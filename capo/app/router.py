"""Decide quale agente deve gestire una richiesta."""
from __future__ import annotations

import re
from dataclasses import dataclass

import logging

import yaml

from . import locale

log = logging.getLogger("uvicorn.error")


@dataclass
class Decisione:
    categoria: str
    agente: str
    modello: str | None   # alias LiteLLM (None per i gestori speciali)
    gestore: str | None   # es. "runpod"
    workflow: str | None
    motivo: str
    endpoint: str | None = None
    parametri: dict | None = None
    serve_web: bool = False
    motivo_web: str = ""
    max_contesto_web: int = 12000
    testo_pulito: str | None = None  # messaggio senza il comando forzato
    domanda_web: str | None = None   # testo da usare per la ricerca web (se diverso dall'ultimo messaggio)


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
            endpoint=c.get("endpoint"),
            parametri=c.get("parametri"),
            max_contesto_web=int(c.get("max_contesto_web", self.regole.get("ricerca_web", {}).get("max_caratteri", 12000))),
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
    def _testo(m: dict) -> str:
        c = m.get("content", "")
        if isinstance(c, list):
            return " ".join(p.get("text", "") for p in c if p.get("type") == "text")
        return c or ""

    def _categoria_precedente(self, messages: list[dict]) -> tuple[str | None, bool, str]:
        """Dalla risposta precedente del Capo: (categoria, usava il web, domanda originale)."""
        categoria, web, domanda = None, False, ""
        visto_assistente = False
        for m in reversed(messages[:-1]):
            if m.get("role") == "assistant" and not visto_assistente:
                visto_assistente = True
                testo = self._testo(m)
                trovato = re.search(r"\*\*Capo\*\* → (.+?) · ", testo)
                if trovato:
                    agente = trovato.group(1).strip()
                    categoria = next((n for n, c in self.categorie.items() if c.get("agente") == agente), None)
                web = "🔎 web" in testo[:400] or "**Fonti:**" in testo
            elif m.get("role") == "user" and visto_assistente:
                t = self._testo(m).strip()
                if not self._e_approfondimento(t, controlla_lunghezza=False):
                    domanda = t
                    break
        return categoria, web, domanda

    def _e_approfondimento(self, testo: str, controlla_lunghezza: bool = True) -> bool:
        cfg = self.regole.get("approfondimento") or {}
        if not cfg.get("attivo", False):
            return False
        if controlla_lunghezza and len(testo) > int(cfg.get("max_lunghezza", 250)):
            return False
        minuscolo = testo.lower()
        return any(p.lower() in minuscolo for p in cfg.get("parole_chiave", []) or [])

    @staticmethod
    def lunghezza_totale(messages: list[dict]) -> int:
        return sum(len(str(m.get("content", ""))) for m in messages)

    # ---------------------------------------------------------------
    async def decidi(self, messages: list[dict]) -> Decisione:
        testo = self.ultimo_messaggio(messages)
        d = await self._scegli_agente(messages, testo)
        if not self.regole.get("ricerca_web", {}).get("attiva", True) or d.gestore in ("runpod", "runpod_pubblico"):
            return d
        if not d.serve_web and d.domanda_web is None:
            motivo = self._serve_web(d.testo_pulito if d.testo_pulito is not None else testo)
            if motivo:
                d.serve_web, d.motivo_web = True, motivo
        return d

    def _serve_web(self, testo: str) -> str:
        """Regole veloci per capire se serve internet. Restituisce il motivo, o stringa vuota."""
        if re.search(r"https?://\S+", testo):
            return "link nel messaggio"
        minuscolo = testo.lower()
        for parola in self.regole.get("ricerca_web", {}).get("parole_chiave", []) or []:
            if parola.lower() in minuscolo:
                return f"parola chiave «{parola}»"
        return ""

    async def _scegli_agente(self, messages: list[dict], testo: str) -> Decisione:
        minuscolo = testo.lower().strip()

        # 0. @web davanti: serve internet, l'agente si sceglie sul resto del messaggio
        cmd_web = self.regole.get("ricerca_web", {}).get("comando", "@web")
        if cmd_web and minuscolo.startswith(cmd_web):
            resto = testo.strip()[len(cmd_web):].strip()
            d = await self._scegli_agente(messages[:-1] + [{"role": "user", "content": resto}], resto)
            d.testo_pulito = d.testo_pulito if d.testo_pulito is not None else resto
            d.serve_web, d.motivo_web = True, f"comando {cmd_web}"
            return d

        # 1. Comando forzato
        for nome, c in self.categorie.items():
            cmd = c.get("comando")
            if cmd and minuscolo.startswith(cmd.lower()):
                return self._decisione(nome, f"comando {cmd}", testo.strip()[len(cmd):].strip())

        # 2. Testo molto lungo
        if self.lunghezza_totale(messages) > self.regole.get("soglia_testo_lungo", 30000):
            return self._decisione("documenti_lunghi", "testo molto lungo")

        # 3. Richiesta di approfondimento della risposta precedente
        if any(m.get("role") == "assistant" for m in messages) and self._e_approfondimento(testo):
            cfg = self.regole["approfondimento"]
            prima, web, domanda = self._categoria_precedente(messages)
            nuova = (cfg.get("scala") or {}).get(prima) if prima else cfg.get("predefinita", "ragionamento")
            if prima and not nuova:
                nuova = prima  # già al livello più alto previsto: resta sullo stesso agente
            d = self._decisione(nuova, "approfondimento")
            if web and domanda:
                d.serve_web, d.motivo_web, d.domanda_web = True, "come la risposta precedente", domanda
            elif domanda:
                d.domanda_web = domanda
            return d

        # 4. Parole chiave
        for nome, c in self.categorie.items():
            for parola in c.get("parole_chiave", []) or []:
                if parola.lower() in minuscolo:
                    return self._decisione(nome, f"parola chiave «{parola}»")

        # 5. Classificazione con il modello locale (sceglie l'agente e se serve internet)
        categoria, web = await self._classifica(testo)
        d = self._decisione(categoria, "valutazione del Capo")
        if web:
            d.serve_web, d.motivo_web = True, "valutazione del Capo"
        return d

    async def _classifica(self, testo: str) -> tuple[str, bool]:
        scelte = {n: c for n, c in self.categorie.items() if not c.get("solo_comando")}
        elenco = "\n".join(
            f"- {n} [{c.get('costo', 'gratis')}]: {c['descrizione']}" for n, c in scelte.items()
        )
        regola = (
            "REGOLA: scegli SEMPRE una categoria [gratis] se può rispondere in modo accettabile. "
            "Scegli una categoria a pagamento solo quando quella gratuita farebbe chiaramente un lavoro scadente. "
            "Nel dubbio, scegli la gratuita.\n\n"
            if self.regole.get("preferisci_gratis", True) else ""
        )
        prompt = (
            "Sei il Capo di un sistema di agenti AI. Classifica la richiesta.\n"
            f"Categorie (tra parentesi il costo):\n{elenco}\n\n"
            f"{regola}"
            "Rispondi con DUE righe, nient'altro:\n"
            "categoria: <nome esatto della categoria>\n"
            "web: <si se servono informazioni aggiornate da internet (notizie, prezzi, risultati, eventi "
            "recenti, documentazione di un prodotto, un sito), altrimenti no>\n\n"
            f"Richiesta:\n{testo[:4000]}"
        )
        try:
            risposta = await locale.chiedi(
                prompt,
                modello_ollama=self.regole.get("modello_locale_ollama", "qwen3:4b-instruct-2507-q4_K_M"),
                alias_litellm=self.regole["classificatore"],
                litellm_url=self.litellm_url,
                litellm_key=self.litellm_key,
                max_tokens=30,
                timeout=60,
            )
        except Exception as e:
            log.warning("Classificazione non riuscita: %r", e)
            return self.regole["predefinita"], False

        risposta = risposta.lower()
        web = bool(re.search(r"web\s*:\s*s[iì]", risposta))
        riga_cat = risposta.split("web")[0]
        for nome in sorted(scelte, key=len, reverse=True):
            if nome in riga_cat:
                log.info("Classificazione: %s, web=%s", nome, web)
                return nome, web
        log.warning("Classificazione non riconosciuta: %r", risposta[:80])
        return self.regole["predefinita"], web
