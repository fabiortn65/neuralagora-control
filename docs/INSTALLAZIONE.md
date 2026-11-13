# Installazione passo passo

## 1. Cosa serve

- **Docker Desktop**: https://docs.docker.com/get-docker/
- **Ollama**: https://ollama.com (installalo normalmente, fuori da Docker)
- Facoltativi: una chiave API Anthropic, una chiave API Gemini, un account RunPod

> Gli abbonamenti Claude Pro e Gemini Pro **non** includono le chiavi API: le API si attivano e si pagano a parte, a consumo, su console.anthropic.com e aistudio.google.com. Senza chiavi il Capo funziona lo stesso, solo con i modelli locali.

## 2. Scarica i modelli locali

Con una scheda video da 6 GB (es. GTX 1660) questi due modelli girano bene:

```bash
ollama pull qwen3:4b-instruct-2507-q4_K_M
ollama pull qwen2.5-coder:3b
```

Se hai più memoria video puoi usare modelli più grandi: cambia i nomi in `litellm/config.yaml`.

## 3. Prepara la configurazione

```bash
cp .env.example .env
```

Apri `.env` e compila:
- `LITELLM_MASTER_KEY`, `WEBUI_SECRET_KEY` e `LITELLM_DB_PASSWORD`: inventa tre stringhe lunghe
- `ANTHROPIC_API_KEY` e `GEMINI_API_KEY`: se le hai
- le variabili `RUNPOD_*`: se usi immagini e video (vedi [`runpod/README.md`](../runpod/README.md))

Il budget massimo per i modelli a pagamento si imposta in `litellm/config.yaml`, alla voce `max_budget`.

## 4. Avvia

```bash
docker compose up -d
```

La prima volta scarica le immagini e richiede qualche minuto.

## 5. Usa

1. Apri **http://localhost:3000**
2. Crea l'account: il primo utente diventa amministratore
3. In alto scegli il modello **🏛️ Capo**
4. Scrivi normalmente: ogni risposta inizia con una riga che dice quale agente ha lavorato

### Comandi per forzare un agente

| Comando | Agente |
|---|---|
| `@locale` | chat locale |
| `@coder` | coder locale |
| `@claude` | Claude |
| `@gemini` | Gemini |
| `@immagine` | generazione immagine |
| `@video` | generazione video |

Esempio: `@claude rivedi l'architettura di questa app`

## 6. Controlla la spesa

**Claude e Gemini** passano da LiteLLM, che registra la spesa in un piccolo database:

- apri **http://localhost:4000/ui**
- utente: `admin`, password: il valore di `LITELLM_MASTER_KEY` nel file `.env`
- nella sezione della spesa (Usage / Spend) vedi quanto ha speso ogni modello

Il tetto `max_budget` in `litellm/config.yaml` (20 $ ogni 30 giorni) viene applicato: superato, le chiamate ai modelli a pagamento vengono bloccate.

**RunPod** (immagini e video) non passa da LiteLLM: la spesa si vede nel saldo e in Billing su runpod.io. Il costo di ogni video compare anche in chat.

Per sicurezza tieni comunque attivi i limiti sulle console dei fornitori (console.anthropic.com, aistudio.google.com).

## Problemi comuni

- **Il Capo risponde sempre "Errore"**: controlla che Ollama sia acceso (`ollama list`) e che `OLLAMA_BASE_URL` in `.env` sia corretto.
- **Su Linux `host.docker.internal` non funziona**: usa l'IP del PC o avvia Ollama dentro Docker con `docker compose --profile ollama up -d` e imposta `OLLAMA_BASE_URL=http://ollama:11434`.
- **Le immagini non si vedono**: l'indirizzo `CAPO_PUBLIC_URL` (predefinito `http://localhost:8100`) deve essere raggiungibile dal tuo browser.
