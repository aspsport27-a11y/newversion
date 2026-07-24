"""Client BRIAPI QRIS — standar SNAP BI (Bank Indonesia).

Alur yang dipakai sistem:
  1. `access_token()` — ambil token B2B. Tanda tangan **asimetris**: RSA-SHA256 atas
     `clientId|timestamp` memakai private key kita. Token di-cache di memori.
  2. `generate_qr()` — MPM Dinamis: bikin QR dengan nominal terkunci per transaksi.
     Tanda tangan **simetris**: HMAC-SHA512 memakai client secret.
  3. `query_qr()` — tanya status pembayaran (dipakai sbg cadangan kalau webhook
     telat/tidak sampai, dan saat kasir menekan "Cek status").

Kalau kredensial belum diisi di .env, semua fungsi melempar `BriNotConfigured`
supaya pemanggil bisa jatuh balik ke perilaku lama (QRIS pending manual).

Catatan penting soal waktu: SNAP minta timestamp ISO-8601 **dengan offset zona**.
Server menyimpan UTC, jadi di sini selalu dikonversi ke WIB (+07:00) — jangan
pakai `datetime.utcnow()` mentah, tanda tangan akan ditolak BRI.
"""
import base64
import hashlib
import hmac
import json
import logging
import threading
import time
from datetime import datetime, timedelta, timezone

import requests
from flask import current_app

log = logging.getLogger(__name__)

WIB = timezone(timedelta(hours=7))

# endpoint relatif — dipakai apa adanya saat menyusun string tanda tangan
PATH_TOKEN = "/snap/v1.0/access-token/b2b"
PATH_QR_GENERATE = "/v1.0/qr/qr-mpm-generate"
PATH_QR_QUERY = "/v1.0/qr/qr-mpm-query"


class BriError(Exception):
    """Panggilan ke BRI gagal (jaringan, kredensial, atau responseCode non-2xx)."""

    def __init__(self, message, code=None, payload=None):
        super().__init__(message)
        self.code = code
        self.payload = payload or {}


class BriNotConfigured(BriError):
    """Kredensial BRI belum lengkap di .env — integrasi dianggap mati."""


# ------------------------------------------------------------------
# Util
# ------------------------------------------------------------------
def _cfg(key):
    return current_app.config.get(key) or ""


def is_configured() -> bool:
    """True kalau semua kredensial wajib sudah terisi."""
    need = [
        "BRI_CLIENT_ID", "BRI_CLIENT_SECRET", "BRI_PARTNER_ID",
        "BRI_PRIVATE_KEY_PATH", "BRI_MERCHANT_ID",
    ]
    return all(_cfg(k) for k in need)


def _require_config():
    if not is_configured():
        raise BriNotConfigured("Kredensial BRIAPI belum diisi di .env")


def now_wib() -> datetime:
    return datetime.now(WIB)


def _timestamp(dt: datetime = None) -> str:
    """Timestamp SNAP: ISO-8601 presisi detik + offset zona.

    Contoh: 2026-07-24T13:05:00+07:00. `isoformat` pada datetime ber-timezone
    sudah menghasilkan offset bergaya `+07:00` (pakai titik dua) sesuai SNAP.
    """
    return (dt or now_wib()).isoformat(timespec="seconds")


def _minify(body: dict) -> str:
    """JSON tanpa spasi — WAJIB sama persis dengan yang dikirim, kalau tidak
    hash body beda dan tanda tangan ditolak."""
    return json.dumps(body, separators=(",", ":"), ensure_ascii=False)


def _body_hash(body_str: str) -> str:
    return hashlib.sha256(body_str.encode("utf-8")).hexdigest().lower()


def _symmetric_signature(method: str, path: str, token: str, body_str: str, ts: str) -> str:
    """HMAC-SHA512 atas `METHOD:path:token:sha256(body):timestamp`, base64."""
    string_to_sign = f"{method}:{path}:{token}:{_body_hash(body_str)}:{ts}"
    digest = hmac.new(
        _cfg("BRI_CLIENT_SECRET").encode("utf-8"),
        string_to_sign.encode("utf-8"),
        hashlib.sha512,
    ).digest()
    return base64.b64encode(digest).decode()


def _asymmetric_signature(client_id: str, ts: str) -> str:
    """RSA-SHA256 atas `clientId|timestamp` dgn private key kita, base64."""
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding

    path = _cfg("BRI_PRIVATE_KEY_PATH")
    try:
        with open(path, "rb") as fh:
            key = serialization.load_pem_private_key(fh.read(), password=None)
    except OSError as e:
        raise BriNotConfigured(f"Private key BRI tidak terbaca ({path}): {e}")

    signature = key.sign(
        f"{client_id}|{ts}".encode("utf-8"),
        padding.PKCS1v15(),
        hashes.SHA256(),
    )
    return base64.b64encode(signature).decode()


# ------------------------------------------------------------------
# Access token (di-cache; token SNAP umumnya berlaku ~15 menit)
# ------------------------------------------------------------------
_token_lock = threading.Lock()
_token_cache = {"value": None, "expires_at": 0.0}


def access_token(force: bool = False) -> str:
    _require_config()
    with _token_lock:
        if not force and _token_cache["value"] and time.time() < _token_cache["expires_at"]:
            return _token_cache["value"]

        ts = _timestamp()
        client_id = _cfg("BRI_CLIENT_ID")
        url = _cfg("BRI_BASE_URL").rstrip("/") + PATH_TOKEN
        headers = {
            "Content-Type": "application/json",
            "X-TIMESTAMP": ts,
            "X-CLIENT-KEY": client_id,
            "X-SIGNATURE": _asymmetric_signature(client_id, ts),
        }
        try:
            r = requests.post(
                url, headers=headers, json={"grantType": "client_credentials"},
                timeout=current_app.config.get("BRI_TIMEOUT", 15),
            )
        except requests.RequestException as e:
            raise BriError(f"Gagal menghubungi BRI (access token): {e}")

        data = _json_or_error(r, "access token")
        token = data.get("accessToken")
        if not token:
            raise BriError("BRI tidak mengembalikan accessToken", payload=data)

        # kurangi 60 detik sbg penyangga supaya tak kepakai tepat saat kedaluwarsa
        try:
            ttl = int(str(data.get("expiresIn") or 900))
        except (TypeError, ValueError):
            ttl = 900
        _token_cache["value"] = token
        _token_cache["expires_at"] = time.time() + max(ttl - 60, 30)
        return token


def _json_or_error(resp, what):
    try:
        data = resp.json()
    except ValueError:
        raise BriError(f"Respons BRI bukan JSON ({what}): HTTP {resp.status_code}")
    if resp.status_code >= 400:
        raise BriError(
            f"BRI menolak {what}: {data.get('responseMessage') or resp.status_code}",
            code=data.get("responseCode"), payload=data,
        )
    return data


# ------------------------------------------------------------------
# Pemanggilan transaksional (tanda tangan simetris)
# ------------------------------------------------------------------
def _post_signed(path: str, body: dict, external_id: str, what: str) -> dict:
    _require_config()
    token = access_token()
    body_str = _minify(body)
    ts = _timestamp()
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
        "X-TIMESTAMP": ts,
        "X-SIGNATURE": _symmetric_signature("POST", path, token, body_str, ts),
        "X-PARTNER-ID": _cfg("BRI_PARTNER_ID"),
        "X-EXTERNAL-ID": external_id,
        "CHANNEL-ID": _cfg("BRI_CHANNEL_ID"),
    }
    url = _cfg("BRI_BASE_URL").rstrip("/") + path
    try:
        # kirim body_str mentah, BUKAN json=body — supaya byte-nya identik
        # dengan yang dipakai menghitung tanda tangan
        r = requests.post(
            url, headers=headers, data=body_str.encode("utf-8"),
            timeout=current_app.config.get("BRI_TIMEOUT", 15),
        )
    except requests.RequestException as e:
        raise BriError(f"Gagal menghubungi BRI ({what}): {e}")
    return _json_or_error(r, what)


def generate_qr(partner_reference_no: str, amount, external_id: str,
                ttl_seconds: int = None) -> dict:
    """QRIS MPM Dinamis — QR dengan nominal terkunci.

    Mengembalikan dict: qr_content, bri_reference_no, expires_at (datetime WIB),
    dan `raw` (respons penuh untuk jejak audit).
    """
    ttl = ttl_seconds or current_app.config.get("BRI_QR_TTL_SECONDS", 900)
    expires_at = now_wib() + timedelta(seconds=ttl)
    body = {
        "partnerReferenceNo": partner_reference_no,
        "amount": {"value": f"{float(amount):.2f}", "currency": "IDR"},
        "merchantId": _cfg("BRI_MERCHANT_ID"),
        "validityPeriod": _timestamp(expires_at),
    }
    if _cfg("BRI_TERMINAL_ID"):
        body["terminalId"] = _cfg("BRI_TERMINAL_ID")

    data = _post_signed(PATH_QR_GENERATE, body, external_id, "generate QR")
    qr_content = data.get("qrContent") or data.get("qrString") or data.get("qrImage")
    if not qr_content:
        raise BriError("BRI tidak mengembalikan konten QR", payload=data)
    return {
        "qr_content": qr_content,
        "bri_reference_no": data.get("referenceNo"),
        "expires_at": expires_at,
        "raw": data,
    }


# status QRIS dari BRI → status internal kita
_PAID_CODES = {"00", "SUCCESS", "PAID", "SETTLED"}
_FAILED_CODES = {"EXPIRED", "CANCELLED", "FAILED", "REJECTED"}


def normalize_status(latest_transaction_status: str, response_code: str = "") -> str:
    """Terjemahkan status BRI → 'paid' | 'failed' | 'pending'.

    `latestTransactionStatus` SNAP: 00=sukses, 01=pending, 02=batal/gagal,
    03=proses, 05=expired, 06=refund. Nilai tak dikenal → pending (aman:
    pembayaran tidak diakui sampai benar-benar terbukti lunas).
    """
    s = (latest_transaction_status or "").strip().upper()
    if s == "00":
        return "paid"
    if s in ("02", "05", "06"):
        return "failed"
    if s in ("01", "03", "04"):
        return "pending"
    if s in _PAID_CODES:
        return "paid"
    if s in _FAILED_CODES:
        return "failed"
    return "pending"


def query_qr(partner_reference_no: str, external_id: str,
             bri_reference_no: str = None) -> dict:
    """Tanya status pembayaran QR ke BRI. Dipakai sbg cadangan webhook."""
    body = {
        "originalPartnerReferenceNo": partner_reference_no,
        "merchantId": _cfg("BRI_MERCHANT_ID"),
        "serviceCode": "17",  # 17 = QR MPM
    }
    if bri_reference_no:
        body["originalReferenceNo"] = bri_reference_no
    if _cfg("BRI_TERMINAL_ID"):
        body["terminalId"] = _cfg("BRI_TERMINAL_ID")

    data = _post_signed(PATH_QR_QUERY, body, external_id, "query QR")
    return {
        "status": normalize_status(
            data.get("latestTransactionStatus"), data.get("responseCode")
        ),
        "bri_reference_no": data.get("referenceNo") or bri_reference_no,
        "raw": data,
    }


# ------------------------------------------------------------------
# Verifikasi tanda tangan notifikasi (webhook) dari BRI
# ------------------------------------------------------------------
def verify_notification(method: str, path: str, body_str: str,
                        timestamp: str, signature: str, token: str = "") -> bool:
    """Verifikasi HMAC-SHA512 pada notifikasi masuk, tahan timing attack.

    PENTING: skema tanda tangan notifikasi BRI perlu dicocokkan dengan dokumen
    "MPM Notifikasi" milik merchant (sebagian memakai access token di string,
    sebagian string kosong). Karena itu dicoba kedua varian — keduanya tetap
    butuh client secret yang benar, jadi tidak melemahkan keamanan.
    """
    if not _cfg("BRI_CLIENT_SECRET") or not signature:
        return False
    for tok in ({token, ""} if token else {""}):
        expected = _symmetric_signature(method, path, tok, body_str, timestamp)
        if hmac.compare_digest(expected, signature):
            return True
    return False
