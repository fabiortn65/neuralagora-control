# RunPod: immagini e video

Il Capo usa **RunPod Serverless** con il worker ufficiale **worker-comfyui**: paghi solo i secondi in cui la GPU lavora, senza Pod da accendere e spegnere.

## Come si collega un workflow

1. Crea il workflow in ComfyUI (anche sul tuo PC).
2. Esportalo con **Workflow → Export (API)**.
3. Salvalo in `runpod/workflows/` con il nome `immagine.json` o `video.json`.
4. Nel nodo del prompt metti il testo `{{PROMPT}}`, e nel seed metti `"{{SEED}}"` (con le virgolette).

Il Capo sostituisce questi segnaposto prima di inviare il lavoro.

## Workflow incluso

`immagine.json` è un workflow SDXL di base. Funziona con l'immagine di worker-comfyui che contiene il checkpoint `sd_xl_base_1.0.safetensors`. Se usi un altro modello (es. Flux), sostituisci il workflow con quello esportato da te.

## Workflow FLUX.1 schnell

`immagine-flux-schnell.json` funziona con l'immagine `runpod/worker-comfyui:5.8.5-flux1-schnell`: 4 passaggi, veloce ed economico. Per usarlo al posto di SDXL rinominalo in `immagine.json` (o mettilo come `immagine.json` nella tua cartella privata).

## Video

`video.json` non è incluso: i workflow video cambiano molto in base al modello scelto (Wan, LTX, CogVideoX…). Quando hai il tuo workflow, esportalo in formato API, aggiungi i segnaposto e crea un secondo endpoint con `RUNPOD_VIDEO_ENDPOINT_ID`.
