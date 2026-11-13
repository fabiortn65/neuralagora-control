"""Agente web: Gemini con ricerca Google e lettura dei link (URL context), chiamato direttamente."""
from __future__ import annotations

import logging
import os

import httpx

log = logging.getLogger("uvicorn.error")
GEMINI_API = os.getenv("GEMINI_API_URL", "https://generativelanguage.googleapis.com/v1beta")


class WebNonConfigurato(Exception):
    pass


def _testo(contenuto) -> str:
    if isinstance(contenuto, list):
        return " ".join(p.get("text", "") for p in contenuto if isinstance(p, dict) and p.get("type") == "text")
    return str(contenuto or "")


def _in_formato_gemini(messages: list[dict], max_messaggi: int = 12) -> tuple[str, list[dict]]:
    sistema = "\n".join(_testo(m.get("content")) for m in messages if m.get("role") == "system")
    contenuti = []
    for m in [m for m in messages if m.get("role") in ("user", "assistant")][-max_messaggi:]:
        testo = _testo(m.get("content")).strip()
        if testo:
            contenuti.append({"role": "user" if m["role"] == "user" else "model", "parts": [{"text": testo}]})
    return sistema, contenuti


async def chiedi(messages: list[dict], modello: str, max_fonti: int = 6) -> tuple[str, list[tuple[str, str]]]:
    """Restituisce (risposta, [(titolo, url), ...])."""
    chiave = os.getenv("GEMINI_API_KEY")
    if not chiave:
        raise WebNonConfigurato("Per navigare serve GEMINI_API_KEY nel file .env.")
    sistema, contenuti = _in_formato_gemini(messages)
    corpo = {
        "contents": contenuti,
        "tools": [{"google_search": {}}, {"url_context": {}}],
    }
    if sistema:
        corpo["systemInstruction"] = {"parts": [{"text": sistema}]}

    async with httpx.AsyncClient(timeout=180) as client:
        r = await client.post(
            f"{GEMINI_API}/models/{modello}:generateContent",
            headers={"x-goog-api-key": chiave},
            json=corpo,
        )
    if r.status_code != 200:
        raise RuntimeError(f"Gemini ha risposto {r.status_code}: {r.text[:300]}")
    dati = r.json()
    candidato = (dati.get("candidates") or [{}])[0]
    parti = (candidato.get("content") or {}).get("parts") or []
    risposta = "".join(p.get("text", "") for p in parti).strip()

    fonti: list[tuple[str, str]] = []
    visti = set()
    for chunk in (candidato.get("groundingMetadata") or {}).get("groundingChunks") or []:
        web = chunk.get("web") or {}
        url, titolo = web.get("uri"), web.get("title") or web.get("uri")
        if url and url not in visti:
            visti.add(url)
            fonti.append((titolo, url))
    for meta in (candidato.get("urlContextMetadata") or {}).get("urlMetadata") or []:
        url = meta.get("retrievedUrl")
        if url and url not in visti:
            visti.add(url)
            fonti.append((url, url))
    return risposta, fonti[:max_fonti]
