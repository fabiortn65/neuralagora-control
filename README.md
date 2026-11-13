# 🏛️ Neural Agorà Control

**Una piattaforma open source in cui un'IA "Capo" riceve ogni richiesta e la smista al modello più adatto: locale, cloud o GPU on-demand.**

*[English version below](#-english)*

---

## Come funziona

```
                 ┌──────────────────────────────┐
  Tu  ──────────▶│  Open WebUI (interfaccia)    │
                 └──────────────┬───────────────┘
                                ▼
                 ┌──────────────────────────────┐
                 │  IL CAPO (router)            │  1. classifica la richiesta
                 │  capo/                       │  2. sceglie l'agente
                 └──────────────┬───────────────┘  3. ti dice chi sta lavorando
                                ▼
                 ┌──────────────────────────────┐
                 │  LiteLLM (gateway + budget)  │
                 └──┬───────────┬───────────┬───┘
                    ▼           ▼           ▼
              Ollama locale   Claude      Gemini          RunPod Serverless
              (gratis)        (codice     (documenti      (immagini e video
                              complesso)  lunghi)          con ComfyUI)
```

| Tipo di richiesta | Agente | Costo |
|---|---|---|
| Chat, domande semplici | 💬 Locale (Ollama) | 0 € |
| Codice semplice | 🧑‍💻 Coder locale (Ollama) | 0 € |
| Codice complesso, architettura, debug | 🧠 Claude | API a consumo |
| Documenti molto lunghi, sintesi | 📚 Gemini Flash | API a consumo (basso) |
| Immagini | 🎨 ComfyUI su RunPod | solo i secondi di GPU |
| Video | 🎬 ComfyUI su RunPod | solo i secondi di GPU |

Le regole di smistamento sono in [`capo/rules.yaml`](capo/rules.yaml): si modificano senza toccare il codice.

## Principi

- **Prima il locale.** Tutto ciò che un modello piccolo sa fare bene resta sul tuo PC, gratis.
- **Porta la tua chiave (BYOK).** Ognuno usa le proprie chiavi API. Senza chiavi funziona comunque, solo in locale.
- **Budget sotto controllo.** LiteLLM registra la spesa per modello e blocca le chiamate oltre il limite.
- **Trasparenza.** Ogni risposta indica quale agente ha lavorato e perché.

## Avvio rapido

Requisiti: [Docker](https://docs.docker.com/get-docker/) e [Ollama](https://ollama.com) installati.

```bash
git clone https://github.com/<tuo-utente>/neuralagora-control.git
cd neuralagora-control
cp .env.example .env          # poi inserisci le tue chiavi (facoltative)
ollama pull qwen3:4b-instruct-2507-q4_K_M          # modello per chat e classificazione
ollama pull qwen2.5-coder:3b  # modello per il codice
docker compose up -d
```

Apri **http://localhost:3000**, crea l'account amministratore e scegli il modello **🏛️ Capo**.

Guida completa passo passo: [`docs/INSTALLAZIONE.md`](docs/INSTALLAZIONE.md)

## Struttura

```
capo/            Il Capo: router compatibile OpenAI (FastAPI)
  rules.yaml     Regole di smistamento (modificabili)
litellm/         Configurazione del gateway: modelli, alias, budget
runpod/          Client e workflow ComfyUI per immagini e video
docs/            Guide in italiano
```

## Roadmap

- [x] Router con classificazione locale e regole configurabili
- [x] Gateway LiteLLM con budget
- [x] Immagini su RunPod Serverless
- [ ] Video su RunPod Serverless (workflow da completare)
- [ ] Integrazione GitHub via MCP
- [ ] Passaggio dei lavori di codice a Claude Code
- [ ] Memoria persistente delle conversazioni

## Licenza

[AGPL-3.0](LICENSE): libero da usare, modificare e condividere. Chi lo offre come servizio online deve pubblicare le proprie modifiche.

---

## 🇬🇧 English

**Neural Agorà Control** is an open source platform where a "Boss" AI receives every request and routes it to the best model: local (Ollama), cloud (Claude, Gemini) or on-demand GPU (RunPod for images and video).

- **Local first**: simple chat and easy code stay on your machine, for free.
- **Bring your own key**: everyone uses their own API keys; without keys it runs fully local.
- **Budget control** through LiteLLM.
- **Transparency**: every answer says which agent worked on it.

Quick start: see the commands above. Routing rules live in `capo/rules.yaml`. License: AGPL-3.0.
