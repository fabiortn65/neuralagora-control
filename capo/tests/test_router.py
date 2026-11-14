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


def _storia(agente, web=False):
    intest = f"> 🏛️ **Capo** → {agente} · *valutazione del Capo*" + (" · 🔎 web (*link nel messaggio*)" if web else "")
    return [
        {"role": "user", "content": "https://github.com/latent-spaces/brag a cosa serve?"},
        {"role": "assistant", "content": intest + "\n\nServe a ...\n\n**Fonti:**\n- [x](https://x)" if web else intest + "\n\nRisposta"},
    ]


def test_approfondimento_da_locale_passa_a_haiku_con_web():
    d = decidi("approfondisci", extra=_storia("💬 Locale", web=True))
    assert d.categoria == "ragionamento"
    assert d.motivo == "approfondimento"
    assert d.serve_web
    assert "latent-spaces/brag" in d.domanda_web


def test_approfondimento_da_haiku_passa_a_claude():
    d = decidi("spiegami meglio", extra=_storia("⚡ Claude Haiku"))
    assert d.categoria == "codice_complesso"
    assert not d.serve_web


def test_approfondimento_doppio_ritrova_la_domanda_originale():
    storia = _storia("💬 Locale", web=True) + [
        {"role": "user", "content": "approfondisci"},
        {"role": "assistant", "content": "> 🏛️ **Capo** → ⚡ Claude Haiku · *approfondimento* · 🔎 web (*come la risposta precedente*)\n\nDettagli"},
    ]
    d = decidi("vai più a fondo", extra=storia)
    assert d.categoria == "codice_complesso"
    assert "latent-spaces/brag" in d.domanda_web


def test_approfondisci_senza_risposta_precedente_non_scala():
    d = decidi("approfondisci il tema delle energie rinnovabili")
    assert d.categoria == "chat"


FOTO = "data:image/png;base64," + "A" * 200000  # come la manda Open WebUI


def _con_foto(testo):
    return [{"role": "user", "content": [
        {"type": "text", "text": testo},
        {"type": "image_url", "image_url": {"url": FOTO}},
    ]}]


def test_foto_allegata_non_e_testo_lungo():
    d = asyncio.run(router.decidi(_con_foto("che ne pensi di questa foto?")))
    assert d.categoria != "documenti_lunghi"


def test_anima_foto_allegata():
    d = asyncio.run(router.decidi(_con_foto("anima questa foto: cammina verso la palestra")))
    assert d.categoria == "anima_foto"
    assert d.endpoint == "wan-2-2-i2v-720"
    assert d.immagine == FOTO
    assert not d.serve_web


def test_modifica_foto_allegata_con_comando():
    d = asyncio.run(router.decidi(_con_foto("@modifica mettile un abito sportivo nero")))
    assert d.categoria == "modifica_foto"
    assert d.campo_immagine == "images"
    assert d.immagine == FOTO


def test_anima_senza_foto_non_usa_la_categoria():
    d = decidi("anima questa foto")
    assert d.categoria != "anima_foto"


def test_anima_l_ultima_foto_modificata():
    storia = _con_foto("modifica questa foto: abito sportivo") + [
        {"role": "assistant", "content": "> 🏛️ **Capo** → 🖌️ Qwen Image Edit (RunPod) · *parola chiave*\n\n"
         "![risultato](http://100.94.101.93:8100/output/1_x.png)\n\n"
         "[🔗 Originale su RunPod (valido 7 giorni)](https://cdn.runpod.example/edit.png)"},
    ]
    d = decidi("ora animala: cammina sul marciapiede", extra=storia)
    assert d.categoria == "anima_foto"
    assert d.immagine == "https://cdn.runpod.example/edit.png"


def test_link_google_drive():
    d = decidi("anima questa foto https://drive.google.com/file/d/1AbCdEfGhIjKlMnOp/view?usp=sharing")
    assert d.categoria == "anima_foto"
    assert d.immagine == "https://drive.google.com/uc?export=download&id=1AbCdEfGhIjKlMnOp"
