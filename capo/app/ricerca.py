"""Ricerca sul web per tutti gli agenti: SearXNG (gratuito, in Docker) + lettura delle pagine."""
from __future__ import annotations

import asyncio
import logging
import os
import re
from html.parser import HTMLParser

import httpx

log = logging.getLogger("uvicorn.error")
SEARXNG_URL = os.getenv("SEARXNG_URL", "http://searxng:8080").rstrip("/")
UA = "Mozilla/5.0 (compatible; NeuralAgoraControl/1.0)"
RE_URL = re.compile(r"https?://[^\s<>\"')\]]+")


class _Testo(HTMLParser):
    """Estrae il testo leggibile da una pagina HTML (senza script, stili, menu)."""
    SALTA = {"script", "style", "noscript", "nav", "footer", "header", "svg", "form", "aside"}

    def __init__(self):
        super().__init__()
        self.parti: list[str] = []
        self.titolo = ""
        self._profondita_saltata = 0
        self._in_titolo = False

    def handle_starttag(self, tag, attrs):
        if tag in self.SALTA:
            self._profondita_saltata += 1
        if tag == "title":
            self._in_titolo = True
        if tag in ("p", "br", "li", "h1", "h2", "h3", "h4", "tr", "div", "pre"):
            self.parti.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SALTA and self._profondita_saltata:
            self._profondita_saltata -= 1
        if tag == "title":
            self._in_titolo = False

    def handle_data(self, data):
        if self._in_titolo:
            self.titolo += data
        elif not self._profondita_saltata:
            self.parti.append(data)

    def testo(self) -> str:
        t = "".join(self.parti)
        t = re.sub(r"[ \t\r\f\v]+", " ", t)
        t = re.sub(r"\n\s*\n+", "\n\n", t)
        return t.strip()


def trova_link(testo: str) -> list[str]:
    return [u.rstrip(".,;:") for u in RE_URL.findall(testo or "")]


async def leggi_pagina(client: httpx.AsyncClient, url: str, max_caratteri: int) -> tuple[str, str]:
    """Restituisce (titolo, testo) della pagina. Per GitHub legge direttamente il README."""
    m = re.match(r"https?://github\.com/([^/\s]+)/([^/\s#?]+)/?$", url)
    if m:
        for ramo in ("main", "master"):
            r = await client.get(f"https://raw.githubusercontent.com/{m[1]}/{m[2]}/{ramo}/README.md")
            if r.status_code == 200:
                return f"{m[1]}/{m[2]} (README)", r.text[:max_caratteri]
    r = await client.get(url)
    r.raise_for_status()
    tipo = r.headers.get("content-type", "")
    if "html" not in tipo:
        return url, r.text[:max_caratteri]
    p = _Testo()
    p.feed(r.text)
    return (p.titolo.strip() or url), p.testo()[:max_caratteri]


async def cerca(query: str, n: int = 5) -> list[dict]:
    async with httpx.AsyncClient(timeout=20, headers={"User-Agent": UA}) as client:
        r = await client.get(f"{SEARXNG_URL}/search", params={"q": query, "format": "json", "language": "it"})
        r.raise_for_status()
        risultati = r.json().get("results", [])
    return [{"titolo": x.get("title", ""), "url": x.get("url", ""), "estratto": x.get("content", "")}
            for x in risultati if x.get("url")][:n]


async def contesto_web(messaggio: str, query: str, max_caratteri: int = 12000,
                       pagine: int = 3) -> tuple[str, list[tuple[str, str]]]:
    """Raccoglie dal web il materiale utile: legge i link del messaggio, altrimenti cerca e legge i primi risultati.
    Restituisce (testo di contesto, [(titolo, url)])."""
    blocchi: list[str] = []
    fonti: list[tuple[str, str]] = []
    link = trova_link(messaggio)

    async with httpx.AsyncClient(timeout=20, follow_redirects=True, headers={"User-Agent": UA}) as client:
        if link:
            da_leggere = [(u, u) for u in link[:pagine]]
            risultati = []
        else:
            try:
                risultati = await cerca(query)
            except Exception as e:
                log.warning("Ricerca SearXNG non riuscita: %r", e)
                return "", []
            da_leggere = [(x["url"], x["titolo"]) for x in risultati[:pagine]]

        per_pagina = max(1500, max_caratteri // max(1, len(da_leggere) or 1))
        letture = await asyncio.gather(
            *(leggi_pagina(client, u, per_pagina) for u, _ in da_leggere), return_exceptions=True
        )
        for (url, titolo_ricerca), esito in zip(da_leggere, letture):
            if isinstance(esito, Exception):
                log.info("Pagina non leggibile %s: %r", url, esito)
                continue
            titolo, testo = esito
            if testo:
                blocchi.append(f"### {titolo or titolo_ricerca}\nFonte: {url}\n\n{testo}")
                fonti.append((titolo or titolo_ricerca or url, url))

        # Gli estratti degli altri risultati aggiungono contesto senza leggere le pagine
        for x in risultati[len(da_leggere):]:
            if x["estratto"]:
                blocchi.append(f"### {x['titolo']}\nFonte: {x['url']}\n\n{x['estratto']}")
                fonti.append((x["titolo"] or x["url"], x["url"]))

    testo = "\n\n---\n\n".join(blocchi)[:max_caratteri]
    return testo, fonti
