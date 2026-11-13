import asyncio
from pathlib import Path

from app.router import Router

REGOLE = Path(__file__).resolve().parents[1] / "rules.yaml"
# Porta chiusa: la classificazione LLM fallisce e si usa la categoria predefinita
router = Router(str(REGOLE), "http://127.0.0.1:9", "test")


def decidi(testo, extra=None):
    messages = (extra or []) + [{"role": "user", "content": testo}]
    return asyncio.run(router.decidi(messages))


def test_comando_forzato():
    d = decidi("@claude rivedi questa architettura")
    assert d.categoria == "codice_complesso"
    assert d.modello == "cloud-codice"
    assert d.testo_pulito == "rivedi questa architettura"


def test_parola_chiave_immagine():
    d = decidi("Crea un'immagine di un tramonto su Rieti")
    assert d.categoria == "immagine"
    assert d.gestore == "runpod"


def test_testo_lungo():
    d = decidi("riassumi", extra=[{"role": "user", "content": "x" * 40000}])
    assert d.categoria == "documenti_lunghi"


def test_ripiego_predefinito():
    d = decidi("ciao, come stai?")
    assert d.categoria == "chat"
    assert d.modello == "locale-chat"


def test_formato_multimodale():
    messages = [{"role": "user", "content": [{"type": "text", "text": "@gemini riassumi"}]}]
    d = asyncio.run(router.decidi(messages))
    assert d.categoria == "documenti_lunghi"
