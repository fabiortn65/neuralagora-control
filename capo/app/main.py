"""Il Capo: API compatibile OpenAI che smista ogni richiesta all'agente giusto."""
from __future__ import annotations

import json
import os
import time
import uuid

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import runpod_client
from .router import Decisione, Router

LITELLM_URL = os.getenv("LITELLM_URL", "http://localhost:4000")
LITELLM_KEY = os.getenv("LITELLM_MASTER_KEY", "")
URL_PUBBLICO = os.getenv("CAPO_PUBLIC_URL", "http://localhost:8100").rstrip("/")
NOME_MODELLO = "capo"
HEADERS = {"Authorization": f"Bearer {LITELLM_KEY}"} if LITELLM_KEY else {}

router = Router(os.getenv("RULES_PATH", "/app/rules.yaml"), LITELLM_URL, LITELLM_KEY)
app = FastAPI(title="Neural Agorà Control - Capo")

os.makedirs(runpod_client.CARTELLA_OUTPUT, exist_ok=True)
app.mount("/output", StaticFiles(directory=runpod_client.CARTELLA_OUTPUT), name="output")


# ------------------------------------------------------------------ utilità
def _intestazione(d: Decisione) -> str:
    return f"> 🏛️ **Capo** → {d.agente} · *{d.motivo}*\n\n"


def _e_compito_interfaccia(messages: list[dict]) -> bool:
    """Open WebUI chiede da sola titoli, tag e suggerimenti: li gestisce il locale senza intestazione."""
    testo = Router.ultimo_messaggio(messages)
    return testo.lstrip().startswith("### Task:")


def _chunk(testo: str, fine: bool = False) -> str:
    dati = {
        "id": f"capo-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": NOME_MODELLO,
        "choices": [{"index": 0, "delta": {} if fine else {"content": testo},
                     "finish_reason": "stop" if fine else None}],
    }
    return f"data: {json.dumps(dati, ensure_ascii=False)}\n\n"


def _risposta_completa(testo: str) -> dict:
    return {
        "id": f"capo-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": NOME_MODELLO,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": testo},
                     "finish_reason": "stop"}],
    }


CAMPI_STRUMENTI = ("tools", "tool_choice", "functions", "function_call", "parallel_tool_calls")


def _prepara(corpo: dict) -> dict:
    """Toglie gli strumenti interni dell'interfaccia e aggiunge le istruzioni del Capo."""
    corpo = {k: v for k, v in corpo.items() if k not in CAMPI_STRUMENTI}
    istruzioni = (router.regole.get("istruzioni_sistema") or "").strip()
    if istruzioni:
        corpo["messages"] = [{"role": "system", "content": istruzioni}] + list(corpo.get("messages", []))
    return corpo


def _sostituisci_ultimo_messaggio(messages: list[dict], nuovo: str) -> list[dict]:
    copia = [dict(m) for m in messages]
    for m in reversed(copia):
        if m.get("role") == "user":
            m["content"] = nuovo
            break
    return copia


# ------------------------------------------------------------------ endpoint
@app.get("/v1/models")
async def modelli():
    return {"object": "list", "data": [
        {"id": NOME_MODELLO, "object": "model", "owned_by": "neuralagora-control", "name": "🏛️ Capo"}
    ]}


@app.get("/health")
async def salute():
    return {"ok": True}


@app.post("/v1/chat/completions")
async def chat(request: Request):
    corpo = await request.json()
    messages = corpo.get("messages", [])
    stream = bool(corpo.get("stream"))

    if _e_compito_interfaccia(messages):
        d = router._decisione("chat", "compito interno")
        return await _inoltra(corpo, d, stream, intestazione=False)

    d = await router.decidi(messages)
    if d.testo_pulito is not None:
        corpo["messages"] = _sostituisci_ultimo_messaggio(messages, d.testo_pulito)

    if d.gestore == "runpod":
        return await _multimedia(corpo, d, stream)
    return await _inoltra(corpo, d, stream)


# ------------------------------------------------------------------ testo via LiteLLM
async def _inoltra(corpo: dict, d: Decisione, stream: bool, intestazione: bool = True):
    corpo = {**corpo, "model": d.modello}
    if intestazione:
        corpo = _prepara(corpo)
    else:
        corpo = {k: v for k, v in corpo.items() if k not in CAMPI_STRUMENTI}
    headers = HEADERS
    url = f"{LITELLM_URL}/v1/chat/completions"

    if not stream:
        async with httpx.AsyncClient(timeout=600) as client:
            r = await client.post(url, headers=headers, json=corpo)
        if r.status_code != 200:
            return JSONResponse(_risposta_completa(f"⚠️ Errore da {d.agente}: {r.text[:500]}"))
        dati = r.json()
        if intestazione:
            msg = dati["choices"][0]["message"]
            msg["content"] = _intestazione(d) + (msg.get("content") or "")
        dati["model"] = NOME_MODELLO
        return JSONResponse(dati)

    async def generatore():
        if intestazione:
            yield _chunk(_intestazione(d))
        async with httpx.AsyncClient(timeout=600) as client:
            async with client.stream("POST", url, headers=headers, json=corpo) as r:
                if r.status_code != 200:
                    errore = (await r.aread()).decode(errors="ignore")[:500]
                    yield _chunk(f"⚠️ Errore da {d.agente}: {errore}")
                    yield _chunk("", fine=True)
                    yield "data: [DONE]\n\n"
                    return
                async for riga in r.aiter_lines():
                    if riga:
                        yield riga + "\n\n"

    return StreamingResponse(generatore(), media_type="text/event-stream")


# ------------------------------------------------------------------ immagini e video
async def _prompt_visivo(richiesta: str) -> str:
    """Il modello locale trasforma la richiesta in un prompt visivo in inglese (gratis)."""
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.post(
                f"{LITELLM_URL}/v1/chat/completions",
                headers=HEADERS,
                json={
                    "model": "locale-chat",
                    "temperature": 0.4,
                    "messages": [{"role": "user", "content":
                        "Rewrite this request as one detailed English prompt for an image/video "
                        "generation model. Reply with the prompt only. /no_think\n\n" + richiesta}],
                },
            )
            r.raise_for_status()
            testo = r.json()["choices"][0]["message"]["content"] or ""
            if "</think>" in testo:
                testo = testo.split("</think>")[-1]
            return testo.strip() or richiesta
    except Exception:
        return richiesta


async def _multimedia(corpo: dict, d: Decisione, stream: bool):
    richiesta = Router.ultimo_messaggio(corpo["messages"])

    async def lavora() -> str:
        prompt = await _prompt_visivo(richiesta)
        try:
            files = await runpod_client.esegui(d.workflow, prompt)
        except runpod_client.RunPodNonConfigurato as e:
            return f"⚠️ {e}\n\nPrompt preparato dal Capo:\n\n```\n{prompt}\n```"
        except Exception as e:
            return f"⚠️ Errore durante la generazione: {e}"
        righe = [f"**Prompt usato:** {prompt}\n"]
        for f in files:
            link = f if f.startswith("http") else f"{URL_PUBBLICO}/output/{f}"
            righe.append(f"![risultato]({link})" if d.workflow == "immagine" else f"[▶️ Apri il video]({link})")
        return "\n".join(righe)

    if not stream:
        return JSONResponse(_risposta_completa(_intestazione(d) + await lavora()))

    async def generatore():
        yield _chunk(_intestazione(d) + "⏳ Sto preparando il lavoro su RunPod...\n\n")
        yield _chunk(await lavora())
        yield _chunk("", fine=True)
        yield "data: [DONE]\n\n"

    return StreamingResponse(generatore(), media_type="text/event-stream")
