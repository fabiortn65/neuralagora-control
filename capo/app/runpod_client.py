"""Esegue un workflow ComfyUI su un endpoint RunPod Serverless (worker-comfyui)."""
from __future__ import annotations

import asyncio
import base64
import json
import os
import random
import time
from pathlib import Path

import httpx

RUNPOD_API = os.getenv("RUNPOD_API_URL", "https://api.runpod.ai/v2")
CARTELLA_WORKFLOW = Path(os.getenv("WORKFLOW_DIR", "/app/workflows"))
CARTELLA_OUTPUT = Path(os.getenv("OUTPUT_DIR", "/app/output"))

ENDPOINT_PER_WORKFLOW = {
    "immagine": "RUNPOD_IMAGE_ENDPOINT_ID",
    "video": "RUNPOD_VIDEO_ENDPOINT_ID",
}


class RunPodNonConfigurato(Exception):
    pass


def _carica_workflow(nome: str, prompt: str) -> dict:
    file = CARTELLA_WORKFLOW / f"{nome}.json"
    if not file.exists():
        raise RunPodNonConfigurato(f"Manca il workflow `runpod/workflows/{nome}.json`.")
    testo = file.read_text(encoding="utf-8")
    testo = testo.replace("{{PROMPT}}", json.dumps(prompt)[1:-1])
    testo = testo.replace('"{{SEED}}"', str(random.randint(1, 2**31 - 1)))
    return json.loads(testo)


async def esegui(nome_workflow: str, prompt: str, timeout_s: int = 600) -> list[str]:
    """Restituisce una lista di file salvati in output/ (o URL esterni)."""
    chiave = os.getenv("RUNPOD_API_KEY")
    endpoint = os.getenv(ENDPOINT_PER_WORKFLOW.get(nome_workflow, ""), "")
    if not chiave or not endpoint:
        raise RunPodNonConfigurato(
            "RunPod non è configurato: imposta RUNPOD_API_KEY e l'ID dell'endpoint nel file .env."
        )

    headers = {"Authorization": f"Bearer {chiave}"}
    corpo = {"input": {"workflow": _carica_workflow(nome_workflow, prompt)}}

    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(f"{RUNPOD_API}/{endpoint}/runsync", headers=headers, json=corpo)
        r.raise_for_status()
        dati = r.json()

        # Se il lavoro non è finito entro il runsync, si controlla lo stato finché termina
        inizio = time.time()
        while dati.get("status") in ("IN_QUEUE", "IN_PROGRESS"):
            if time.time() - inizio > timeout_s:
                raise TimeoutError("RunPod non ha terminato in tempo.")
            await asyncio.sleep(3)
            r = await client.get(f"{RUNPOD_API}/{endpoint}/status/{dati['id']}", headers=headers)
            r.raise_for_status()
            dati = r.json()

    if dati.get("status") != "COMPLETED":
        raise RuntimeError(f"RunPod ha restituito lo stato {dati.get('status')}: {dati.get('error', '')}")

    return _salva_output(dati.get("output") or {})


def _salva_output(output: dict) -> list[str]:
    CARTELLA_OUTPUT.mkdir(parents=True, exist_ok=True)
    risultati: list[str] = []
    elementi = output.get("images") or output.get("videos") or []
    for i, el in enumerate(elementi):
        if el.get("type") == "s3_url" or str(el.get("data", "")).startswith("http"):
            risultati.append(el["data"])
            continue
        nome = f"{int(time.time())}_{i}_{el.get('filename', 'output.png')}"
        (CARTELLA_OUTPUT / nome).write_bytes(base64.b64decode(el["data"]))
        risultati.append(nome)
    return risultati


async def esegui_pubblico(endpoint: str, prompt: str, parametri: dict | None = None,
                          timeout_s: int = 900, immagine: str | None = None,
                          campo_immagine: str | None = None) -> tuple[list[str], float | None, str]:
    """Chiama un endpoint pubblico di RunPod (es. wan-2-2-t2v-720) e scarica il risultato.

    I link degli endpoint pubblici scadono dopo 7 giorni: il file viene salvato in output/.
    Se c'è una foto di partenza, va nel campo indicato (`image`, oppure `images` come lista).
    Restituisce (lista di file salvati, costo in USD se indicato, link originale di RunPod).
    """
    chiave = os.getenv("RUNPOD_API_KEY")
    if not chiave:
        raise RunPodNonConfigurato("RunPod non è configurato: imposta RUNPOD_API_KEY nel file .env.")
    headers = {"Authorization": f"Bearer {chiave}"}
    corpo = {"input": {"prompt": prompt, **(parametri or {})}}
    if immagine and campo_immagine:
        corpo["input"][campo_immagine] = [immagine] if campo_immagine == "images" else immagine

    async with httpx.AsyncClient(timeout=300) as client:
        r = await client.post(f"{RUNPOD_API}/{endpoint}/runsync", headers=headers, json=corpo)
        if r.status_code >= 400:
            raise RuntimeError(f"RunPod ha risposto {r.status_code}: {r.text[:300]}")
        dati = r.json()
        inizio = time.time()
        while dati.get("status") in ("IN_QUEUE", "IN_PROGRESS"):
            if time.time() - inizio > timeout_s:
                raise TimeoutError("RunPod non ha terminato in tempo.")
            await asyncio.sleep(5)
            r = await client.get(f"{RUNPOD_API}/{endpoint}/status/{dati['id']}", headers=headers)
            r.raise_for_status()
            dati = r.json()

        if dati.get("status") != "COMPLETED":
            raise RuntimeError(f"RunPod ha restituito lo stato {dati.get('status')}: {dati.get('error', '')}")

        output = dati.get("output") or {}
        url = None
        if isinstance(output, dict):
            url = output.get("result") or output.get("video_url") or output.get("image_url") or output.get("url")
        elif isinstance(output, str):
            url = output
        if not url:
            raise RuntimeError(f"Risposta di RunPod senza link al risultato: {str(output)[:200]}")
        costo = output.get("cost") if isinstance(output, dict) else None

        CARTELLA_OUTPUT.mkdir(parents=True, exist_ok=True)
        estensione = Path(url.split("?")[0]).suffix or ".mp4"
        nome = f"{int(time.time())}_{endpoint}{estensione}"
        try:
            scarico = await client.get(url, timeout=300)
            scarico.raise_for_status()
            (CARTELLA_OUTPUT / nome).write_bytes(scarico.content)
            return [nome], costo, url
        except Exception:
            return [url], costo, url  # se il download fallisce, resta il link (valido 7 giorni)
