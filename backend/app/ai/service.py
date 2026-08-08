"""Pemanggil Anthropic terpusat — dipakai bersama oleh Ask AI (ai/routes.py) &
briefing Radar (admin/routes.py). Menyatukan boilerplate SDK + penanganan error
supaya tak diduplikasi. Model diambil dari env (ANTHROPIC_MODEL) bila tak dioverride."""
import os


class AINotConfigured(Exception):
    """ANTHROPIC_API_KEY belum diset di server."""


class AIError(Exception):
    """Gagal memanggil API (status/koneksi) atau AI menolak menjawab."""


def ai_complete(system, messages, max_tokens=1024, model=None, thinking=False):
    """Panggil Claude sekali, kembalikan teks jawaban. Raise AINotConfigured bila
    key kosong, AIError bila gagal/ditolak."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise AINotConfigured()

    import anthropic

    model = model or os.environ.get("ANTHROPIC_MODEL", "claude-opus-4-8")
    client = anthropic.Anthropic(api_key=api_key)
    kwargs = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system,
        "messages": messages,
    }
    if thinking:
        kwargs["thinking"] = {"type": "adaptive"}
    try:
        resp = client.messages.create(**kwargs)
    except anthropic.APIStatusError as e:
        raise AIError(getattr(e, "message", str(e)))
    except anthropic.APIConnectionError:
        raise AIError("koneksi bermasalah")

    if resp.stop_reason == "refusal":
        raise AIError("__refusal__")
    return "".join(b.text for b in resp.content if b.type == "text")
