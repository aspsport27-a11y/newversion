"""Endpoint AI — konsultasi dengan Claude. Prefix: /api/ai"""
import os

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt, jwt_required

ai_bp = Blueprint("ai", __name__)

# hanya user portal admin (bukan kasir POS) yang boleh pakai Ask AI
ALLOWED_ROLES = {"admin", "head_office", "manager_unit", "admin_unit"}

SYSTEM_PROMPT = (
    "Kamu adalah asisten AI di dalam ASP Sport System, aplikasi manajemen venue olahraga "
    "(POS, karyawan & kasbon, operasional, procurement, payroll, kas & bank, laporan keuangan). "
    "Pengguna yang bertanya adalah admin/manajer venue. Bantu jawab pertanyaan seputar "
    "operasional bisnis, cara pakai sistem, atau analisis singkat. Jawab singkat, jelas, "
    "dan praktis dalam Bahasa Indonesia. Kamu tidak punya akses langsung ke data transaksi "
    "sistem ini — jika pertanyaan butuh angka spesifik, arahkan pengguna ke menu Laporan yang relevan."
)

MAX_HISTORY = 10


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

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return jsonify(
            error="not_configured",
            message="Fitur AI belum dikonfigurasi di server (ANTHROPIC_API_KEY belum diset).",
        ), 503

    history = data.get("history") or []
    messages = []
    for h in history[-MAX_HISTORY:]:
        role = h.get("role")
        content = h.get("content")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": question})

    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    try:
        response = client.messages.create(
            model="claude-opus-4-8",
            max_tokens=2048,
            thinking={"type": "adaptive"},
            system=SYSTEM_PROMPT,
            messages=messages,
        )
    except anthropic.APIStatusError as e:
        return jsonify(error="ai_error", message=f"Gagal menghubungi AI: {e.message}"), 502
    except anthropic.APIConnectionError:
        return jsonify(error="ai_error", message="Gagal menghubungi AI: koneksi bermasalah"), 502

    if response.stop_reason == "refusal":
        return jsonify(error="ai_refusal", message="AI tidak bisa menjawab pertanyaan ini."), 200

    answer = "".join(block.text for block in response.content if block.type == "text")
    return jsonify(answer=answer), 200
