"""Il Capo: API compatibile OpenAI che smista ogni richiesta all'agente giusto."""
from __future__ import annotations

import json
import logging
import os
import time
import uuid

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import locale, ricerca, runpod_client, web
from .router import Decisione, Router

LITELLM_URL = os.getenv("LITELLM_URL", "http://localhost:4000")
LITELLM_KEY = os.getenv("LITELLM_MASTER_KEY", "")
URL_PUBBLICO = os.getenv("CAPO_PUBLIC_URL", "http://localhost:8100").rstrip("/")
NOME_MODELLO = "capo"
log = logging.getLogger("uvicorn.error")
HEADERS = {"Authorization": f"Bearer {LITELLM_KEY}"} if LITELLM_KEY else {}

router = Router(os.getenv("RULES_PATH", "/app/rules.yaml"), LITELLM_URL, LITELLM_KEY)
app = FastAPI(title="Neural Agorà Control - Capo")

os.makedirs(runpod_client.CARTELLA_OUTPUT, exist_ok=True)
app.mount("/output", StaticFiles(directory=runpod_client.CARTELLA_OUTPUT), name="output")


# ------------------------------------------------------------------ utilità
def _intestazione(d: Decisione) -> str:
    web = f" · 🔎 web (*{d.motivo_web}*)" if d.serve_web else ""
    return f"> 🏛️ **Capo** → {d.agente} · *{d.motivo}*{web}\n\n"


def _fonti_md(fonti: list[tuple[str, str]]) -> str:
    if not fonti:
        return ""
    return "\n\n**Fonti:**\n" + "\n".join(f"- [{t.strip() or u}]({u})" for t, u in fonti[:8])


async def _aggiungi_web(corpo: dict, d: Decisione) -> tuple[dict, list[tuple[str, str]], str]:
    """Cerca sul web e inserisce il materiale trovato prima dell'ultima domanda. Restituisce (corpo, fonti, nota)."""
    messaggi = corpo.get("messages", [])
    domanda = Router.ultimo_messaggio(messaggi)
    if d.domanda_web:  # approfondimento: si cerca sulla domanda originale
        domanda = f"{d.domanda_web}\n\n{domanda}"
    try:
        contesto, fonti = await ricerca.contesto_web(domanda, query=(d.domanda_web or domanda)[:300], max_caratteri=d.max_contesto_web)
    except Exception as e:
        log.warning("Ricerca web non riuscita: %r", e)
        contesto, fonti = "", []
    if not contesto:
        return corpo, [], "_(ricerca sul web non riuscita: rispondo con quello che so)_\n\n"
    blocco = {
        "role": "system",
        "content": "Informazioni raccolte ORA dal web per rispondere all'ultima domanda dell'utente. "
                   "Usale come fonte principale, cita le fonti (URL) che usi e segnala se le informazioni "
                   "non bastano. Non dire che non puoi accedere a internet: il Capo lo ha fatto per te.\n\n"
                   + contesto,
    }
    idx = max((i for i, m in enumerate(messaggi) if m.get("role") == "user"), default=len(messaggi))
    nuovi = list(messaggi[:idx]) + [blocco] + list(messaggi[idx:])
    log.info("Web: %d fonti, %d caratteri di contesto", len(fonti), len(contesto))
    return {**corpo, "messages": nuovi}, fonti, ""


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
CAPO_API_KEY = os.getenv("CAPO_API_KEY", "")


def _controlla_chiave(request: Request) -> None:
    """Se CAPO_API_KEY è impostata, il Capo risponde solo a chi la conosce (es. Open WebUI)."""
    if not CAPO_API_KEY:
        return
    if request.headers.get("authorization", "") != f"Bearer {CAPO_API_KEY}":
        raise HTTPException(status_code=401, detail="Chiave del Capo mancante o errata")


@app.get("/v1/models")
async def modelli(request: Request):
    _controlla_chiave(request)
    return {"object": "list", "data": [
        {"id": NOME_MODELLO, "object": "model", "owned_by": "neuralagora-control", "name": "🏛️ Capo"}
    ]}


@app.get("/health")
async def salute():
    return {"ok": True}


@app.post("/v1/chat/completions")
async def chat(request: Request):
    _controlla_chiave(request)
    corpo = await request.json()
    messages = corpo.get("messages", [])
    stream = bool(corpo.get("stream"))

    if _e_compito_interfaccia(messages):
        d = router._decisione("chat", "compito interno")
        return await _inoltra(corpo, d, stream, intestazione=False)

    d = await router.decidi(messages)
    if d.testo_pulito is not None:
        corpo["messages"] = _sostituisci_ultimo_messaggio(messages, d.testo_pulito)

    if d.gestore in ("runpod", "runpod_pubblico"):
        return await _multimedia(corpo, d, stream)
    if d.gestore == "gemini_web":
        return await _web(_prepara(corpo), d, stream)
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
    usa_web = intestazione and d.serve_web

    if not stream:
        fonti, nota = [], ""
        if usa_web:
            corpo, fonti, nota = await _aggiungi_web(corpo, d)
        async with httpx.AsyncClient(timeout=600) as client:
            r = await client.post(url, headers=headers, json=corpo)
        if r.status_code != 200:
            return JSONResponse(_risposta_completa(f"⚠️ Errore da {d.agente}: {r.text[:500]}"))
        dati = r.json()
        if intestazione:
            msg = dati["choices"][0]["message"]
            msg["content"] = _intestazione(d) + nota + (msg.get("content") or "") + _fonti_md(fonti)
        dati["model"] = NOME_MODELLO
        return JSONResponse(dati)

    async def generatore():
        nonlocal corpo
        fonti: list[tuple[str, str]] = []
        if intestazione:
            yield _chunk(_intestazione(d))
        if usa_web:
            yield _chunk("🔎 Cerco sul web...\n\n")
            corpo, fonti, nota = await _aggiungi_web(corpo, d)
            if nota:
                yield _chunk(nota)
        async with httpx.AsyncClient(timeout=600) as client:
            async with client.stream("POST", url, headers=headers, json=corpo) as r:
                if r.status_code != 200:
                    errore = (await r.aread()).decode(errors="ignore")[:500]
                    yield _chunk(f"⚠️ Errore da {d.agente}: {errore}")
                    yield _chunk("", fine=True)
                    yield "data: [DONE]\n\n"
                    return
                async for riga in r.aiter_lines():
                    if not riga:
                        continue
                    if riga.startswith("data:") and '"error"' in riga[:200]:
                        try:
                            dettaglio = json.loads(riga[5:].strip()).get("error")
                        except Exception:
                            dettaglio = riga[5:200]
                        log.warning("Errore in streaming da %s: %s", d.agente, str(dettaglio)[:300])
                        yield _chunk(f"\n\n⚠️ Errore da {d.agente}: {str(dettaglio)[:400]}")
                        yield _chunk("", fine=True)
                        yield "data: [DONE]\n\n"
                        return
                    if riga.strip() == "data: [DONE]" and fonti:
                        yield _chunk(_fonti_md(fonti))
                        fonti = []
                    yield riga + "\n\n"

    return StreamingResponse(generatore(), media_type="text/event-stream")


# ------------------------------------------------------------------ web (Gemini + Google)
async def _web(corpo: dict, d: Decisione, stream: bool):
    async def lavora() -> str:
        try:
            risposta, fonti = await web.chiedi(corpo.get("messages", []), d.modello or "gemini-flash-latest")
        except web.WebNonConfigurato as e:
            return f"⚠️ {e}"
        except Exception as e:
            log.warning("Agente web non riuscito: %r", e)
            return f"⚠️ Errore durante la ricerca sul web: {e}"
        if not risposta:
            return "⚠️ Nessuna risposta dalla ricerca sul web."
        if fonti:
            risposta += "\n\n**Fonti:**\n" + "\n".join(f"- [{t}]({u})" for t, u in fonti)
        return risposta

    if not stream:
        return JSONResponse(_risposta_completa(_intestazione(d) + await lavora()))

    async def generatore():
        yield _chunk(_intestazione(d) + "🔎 Cerco sul web...\n\n")
        yield _chunk(await lavora())
        yield _chunk("", fine=True)
        yield "data: [DONE]\n\n"

    return StreamingResponse(generatore(), media_type="text/event-stream")


# ------------------------------------------------------------------ immagini e video
async def _prompt_visivo(richiesta: str) -> str:
    """Il modello locale trasforma la richiesta in un prompt visivo in inglese (gratis)."""
    try:
        testo = await locale.chiedi(
            "Rewrite this request as one detailed English prompt for an image/video "
            "generation model. Reply with the prompt only, no quotes, no explanations.\n\n" + richiesta,
            modello_ollama=router.regole.get("modello_locale_ollama", "qwen3:4b-instruct-2507-q4_K_M"),
            alias_litellm="locale-chat",
            litellm_url=LITELLM_URL,
            litellm_key=LITELLM_KEY,
            max_tokens=300,
            temperatura=0.4,
        )
    except Exception as e:
        log.warning("Prompt visivo non riuscito: %r", e)
        return richiesta
    testo = testo.strip().strip('"')
    if len(testo) > 800 or testo.lower().startswith(("we are", "okay", "let's", "first,")):
        log.warning("Prompt visivo scartato: sembra un ragionamento, non un prompt")
        return richiesta
    if not testo:
        log.warning("Prompt visivo: risposta vuota dal modello locale")
        return richiesta
    log.info("Prompt visivo: %s", testo[:200])
    return testo


async def _multimedia(corpo: dict, d: Decisione, stream: bool):
    richiesta = Router.ultimo_messaggio(corpo["messages"])

    async def lavora() -> str:
        prompt = await _prompt_visivo(richiesta)
        costo = None
        try:
            if d.gestore == "runpod_pubblico":
                files, costo = await runpod_client.esegui_pubblico(d.endpoint, prompt, d.parametri)
            else:
                files = await runpod_client.esegui(d.workflow, prompt)
        except runpod_client.RunPodNonConfigurato as e:
            return f"⚠️ {e}\n\nPrompt preparato dal Capo:\n\n```\n{prompt}\n```"
        except Exception as e:
            return f"⚠️ Errore durante la generazione: {e}"
        righe = [f"**Prompt usato:** {prompt}\n"]
        for f in files:
            link = f if f.startswith("http") else f"{URL_PUBBLICO}/output/{f}"
            if f.lower().split("?")[0].endswith((".mp4", ".webm", ".mov")):
                righe.append(f"[▶️ Apri il video]({link})")
            else:
                righe.append(f"![risultato]({link})")
        if costo is not None:
            righe.append(f"\n*Costo: {costo:.2f} $*")
        return "\n".join(righe)

    if not stream:
        return JSONResponse(_risposta_completa(_intestazione(d) + await lavora()))

    async def generatore():
        yield _chunk(_intestazione(d) + "⏳ Sto preparando il lavoro su RunPod...\n\n")
        yield _chunk(await lavora())
        yield _chunk("", fine=True)
        yield "data: [DONE]\n\n"

    return StreamingResponse(generatore(), media_type="text/event-stream")
