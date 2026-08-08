"""Endpoint AI — konsultasi dengan Claude. Prefix: /api/ai"""
from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt, get_jwt_identity, jwt_required

from ..extensions import db
from ..models import User
from .context import build_business_context
from .service import AIError, AINotConfigured, ai_complete

ai_bp = Blueprint("ai", __name__)

# hanya user portal admin (bukan kasir POS) yang boleh pakai Ask AI
ALLOWED_ROLES = {"admin", "head_office", "manager_unit", "admin_unit"}

SYSTEM_PROMPT = (
    "Kamu adalah asisten AI di dalam ASP Sport System, aplikasi manajemen venue olahraga "
    "(POS, karyawan & kasbon, operasional, procurement, payroll, kas & bank, laporan keuangan). "
    "Pengguna yang bertanya adalah admin/manajer venue. Bantu jawab pertanyaan seputar "
    "operasional bisnis, cara pakai sistem, atau analisis singkat. Jawab dalam Bahasa Indonesia "
    "yang ringkas, jelas, dan praktis — untuk daftar pakai poin rapi, untuk jawaban pendek 2-4 kalimat.\n\n"
    "Di bawah ini tersedia RINGKASAN DATA TERKINI (sesuai cakupan/venue pengguna) — gunakan "
    "untuk menjawab pertanyaan tentang keadaan sekarang (omzet hari ini & bulan ini per venue, "
    "pertumbuhan, saldo kas, piutang, approval menunggu, hal yang perlu dicek, stok menipis, dll).\n\n"
    "ATURAN PENTING:\n"
    "1. Angka di ringkasan itu NYATA — pakai itu, JANGAN mengarang angka lain.\n"
    "2. Kalau data yang diminta TIDAK ADA di ringkasan (mis. omzet bulan lalu detail, rincian per "
    "kasir jangka panjang, data historis spesifik), katakan JUJUR datanya tak tersedia di sini "
    "lalu arahkan ke menu Laporan yang relevan — jangan menebak.\n"
    "3. SELALU tutup jawaban dengan 1 rekomendasi tindakan konkret yang bisa langsung dilakukan "
    "(kecuali pertanyaan murni 'cara pakai'). Fokus ke angka & tindakan, bukan basa-basi."
)

MAX_HISTORY = 10


def _model_label(model_id):
    """Ubah id model jadi label ramah, mis. claude-haiku-4-5-2025... -> 'Haiku 4.5'."""
    import re

    m = (model_id or "").lower()
    fam = "Opus" if "opus" in m else "Sonnet" if "sonnet" in m else "Haiku" if "haiku" in m else None
    if not fam:
        return model_id or "AI"
    ver = re.search(r"(\d+)-(\d+)", m)
    return f"{fam} {ver.group(1)}.{ver.group(2)}" if ver else fam


@ai_bp.get("/info")
@jwt_required()
def info():
    """Info ringan utk UI Ask AI: apakah AI aktif + label model yg dipakai."""
    import os

    if get_jwt().get("role") not in ALLOWED_ROLES:
        return jsonify(error="forbidden"), 403
    model = os.environ.get("ANTHROPIC_MODEL", "claude-opus-4-8")
    return jsonify(
        configured=bool(os.environ.get("ANTHROPIC_API_KEY")),
        model=model,
        model_label=_model_label(model),
    ), 200


@ai_bp.post("/ask")
@jwt_required()
def ask():
    claims = get_jwt()
    if claims.get("role") not in ALLOWED_ROLES:
        return jsonify(error="forbidden", message="Fitur Ask AI hanya untuk pengguna portal admin"), 403

    data = request.get_json(silent=True) or {}
    question = (data.get("question") or "").strip()
    if not question:
        return jsonify(error="bad_request", message="Pertanyaan wajib diisi"), 400

    user = db.session.get(User, int(get_jwt_identity()))

    # suntik ringkasan data terkini (scoped) supaya AI "melek data"
    system = SYSTEM_PROMPT
    try:
        ctx = build_business_context(user)
        if ctx:
            system = SYSTEM_PROMPT + "\n\n===== DATA =====\n" + ctx
    except Exception:
        pass  # kalau gagal ambil konteks, tetap jawab tanpa data (jangan blokir)

    history = data.get("history") or []
    messages = []
    for h in history[-MAX_HISTORY:]:
        role = h.get("role")
        content = h.get("content")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": question})

    try:
        answer = ai_complete(system, messages, max_tokens=2048, thinking=True)
    except AINotConfigured:
        return jsonify(
            error="not_configured",
            message="Fitur AI belum dikonfigurasi di server (ANTHROPIC_API_KEY belum diset).",
        ), 503
    except AIError as e:
        if str(e) == "__refusal__":
            return jsonify(error="ai_refusal", message="AI tidak bisa menjawab pertanyaan ini."), 200
        return jsonify(error="ai_error", message=f"Gagal menghubungi AI: {e}"), 502

    return jsonify(answer=answer), 200
