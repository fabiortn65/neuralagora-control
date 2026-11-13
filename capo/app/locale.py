"""Chiamate rapide al modello locale per i lavori interni del Capo (classificare, riscrivere prompt).

Si chiama Ollama direttamente con il ragionamento disattivato: i modelli che "pensano"
(es. qwen3) via LiteLLM in modalita' non-streaming possono restituire una risposta vuota.
Se Ollama non risponde, si ripiega su LiteLLM.
"""
from __future__ import annotations

import logging
import os
import re

import httpx

log = logging.getLogger("uvicorn.error")


def _pulisci(testo: str) -> str:
    testo = re.sub(r"<think>.*?</think>", "", testo or "", flags=re.S)
    if "</think>" in testo:
        testo = testo.split("</think>")[-1]
    return testo.strip()


async def chiedi(prompt: str, modello_ollama: str, alias_litellm: str, litellm_url: str,
                 litellm_key: str, max_tokens: int = 300, temperatura: float = 0.0,
                 timeout: float = 120) -> str:
    ollama = os.getenv("OLLAMA_BASE_URL", "").rstrip("/")
    if ollama:
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                r = await client.post(f"{ollama}/api/chat", json={
                    "model": modello_ollama,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                    "think": False,
                    "options": {"temperature": temperatura, "num_predict": max_tokens},
                })
            if r.status_code == 200:
                testo = _pulisci(r.json().get("message", {}).get("content", ""))
                if testo:
                    return testo
                log.warning("Locale: Ollama ha risposto vuoto, provo LiteLLM")
            else:
                log.warning("Locale: Ollama ha risposto %s: %s", r.status_code, r.text[:200])
        except Exception as e:
            log.warning("Locale: Ollama non raggiungibile (%r), provo LiteLLM", e)

    headers = {"Authorization": f"Bearer {litellm_key}"} if litellm_key else {}
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(f"{litellm_url.rstrip('/')}/v1/chat/completions", headers=headers, json={
            "model": alias_litellm,
            "messages": [{"role": "user", "content": prompt + " /no_think"}],
            "temperature": temperatura,
            "max_tokens": max_tokens,
        })
    r.raise_for_status()
    return _pulisci(r.json()["choices"][0]["message"].get("content") or "")
