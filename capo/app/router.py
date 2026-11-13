"""Decide quale agente deve gestire una richiesta."""
from __future__ import annotations

import re
from dataclasses import dataclass

import httpx
import yaml


@dataclass
class Decisione:
    categoria: str
    agente: str
    modello: str | None   # alias LiteLLM (None per i gestori speciali)
    gestore: str | None   # es. "runpod"
    workflow: str | None
    motivo: str
    testo_pulito: str | None = None  # messaggio senza il comando forzato


class Router:
    def __init__(self, percorso_regole: str, litellm_url: str, litellm_key: str):
        with open(percorso_regole, encoding="utf-8") as f:
            self.regole = yaml.safe_load(f)
        self.categorie: dict = self.regole["categorie"]
        self.litellm_url = litellm_url.rstrip("/")
        self.litellm_key = litellm_key

    # ---------------------------------------------------------------
    def _decisione(self, categoria: str, motivo: str, testo_pulito: str | None = None) -> Decisione:
        c = self.categorie.get(categoria) or self.categorie[self.regole["predefinita"]]
        return Decisione(
            categoria=categoria,
            agente=c["agente"],
            modello=c.get("modello"),
            gestore=c.get("gestore"),
            workflow=c.get("workflow"),
            motivo=motivo,
            testo_pulito=testo_pulito,
        )

    @staticmethod
    def ultimo_messaggio(messages: list[dict]) -> str:
        for m in reversed(messages):
            if m.get("role") == "user":
                contenuto = m.get("content", "")
                if isinstance(contenuto, list):  # formato multimodale
                    return " ".join(p.get("text", "") for p in contenuto if p.get("type") == "text")
                return contenuto
        return ""

    @staticmethod
    def lunghezza_totale(messages: list[dict]) -> int:
        return sum(len(str(m.get("content", ""))) for m in messages)

    # ---------------------------------------------------------------
    async def decidi(self, messages: list[dict]) -> Decisione:
        testo = self.ultimo_messaggio(messages)
        minuscolo = testo.lower().strip()

        # 1. Comando forzato
        for nome, c in self.categorie.items():
            cmd = c.get("comando")
            if cmd and minuscolo.startswith(cmd.lower()):
                return self._decisione(nome, f"comando {cmd}", testo.strip()[len(cmd):].strip())

        # 2. Testo molto lungo
        if self.lunghezza_totale(messages) > self.regole.get("soglia_testo_lungo", 30000):
            return self._decisione("documenti_lunghi", "testo molto lungo")

        # 3. Parole chiave
        for nome, c in self.categorie.items():
            for parola in c.get("parole_chiave", []) or []:
                if parola.lower() in minuscolo:
                    return self._decisione(nome, f"parola chiave «{parola}»")

        # 4. Classificazione con il modello locale
        categoria = await self._classifica(testo)
        return self._decisione(categoria, "valutazione del Capo")

    async def _classifica(self, testo: str) -> str:
        elenco = "\n".join(f"- {n}: {c['descrizione']}" for n, c in self.categorie.items())
        prompt = (
            "Sei il Capo di un sistema di agenti AI. Classifica la richiesta in UNA sola categoria.\n"
            f"Categorie:\n{elenco}\n\n"
            "Rispondi solo con il nome esatto della categoria, nient'altro. /no_think\n\n"
            f"Richiesta:\n{testo[:4000]}"
        )
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                r = await client.post(
                    f"{self.litellm_url}/v1/chat/completions",
                    headers={"Authorization": f"Bearer {self.litellm_key}"} if self.litellm_key else {},
                    json={
                        "model": self.regole["classificatore"],
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0,
                        "max_tokens": 200,
                    },
                )
                r.raise_for_status()
                risposta = r.json()["choices"][0]["message"]["content"] or ""
        except Exception:
            return self.regole["predefinita"]

        risposta = re.sub(r"<think>.*?</think>", "", risposta, flags=re.S).strip().lower()
        for nome in self.categorie:
            if nome in risposta:
                return nome
        return self.regole["predefinita"]
