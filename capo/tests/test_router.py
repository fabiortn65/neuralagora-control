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


def test_link_attiva_il_web():
    d = decidi("https://github.com/latent-spaces/brag cosa fa?")
    assert d.serve_web
    assert d.motivo_web == "link nel messaggio"


def test_comando_web_con_agente():
    d = decidi("@web @claude riassumi le novità di Python 3.14")
    assert d.serve_web
    assert d.categoria == "codice_complesso"
    assert d.testo_pulito == "riassumi le novità di Python 3.14"


def test_parola_chiave_web():
    d = decidi("che tempo fa? dimmi il meteo di Rieti")
    assert d.serve_web


def test_immagini_senza_web():
    d = decidi("crea un'immagine del meteo di oggi")
    assert d.categoria == "immagine"
    assert not d.serve_web


def test_domanda_normale_senza_web():
    d = decidi("ciao, come stai?")
    assert not d.serve_web


def test_livelli_claude():
    assert decidi("@haiku scrivimi una mail di ringraziamento").modello == "cloud-veloce"
    assert decidi("@claude progetta il backend").modello == "cloud-codice"
    assert decidi("@opus analizza questa strategia").modello == "cloud-top"


def test_opus_mai_dal_classificatore():
    import asyncio
    elenco = [n for n, c in router.categorie.items() if not c.get("solo_comando")]
    assert "massimo" not in elenco
