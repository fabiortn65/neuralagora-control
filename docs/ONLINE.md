# Usare il Capo da fuori casa (Tailscale) e fare i backup

## Perché Tailscale

Tailscale crea una rete privata tra i **tuoi** dispositivi (PC, telefono, tablet).
Il Capo resta sul tuo PC, nessuna porta del router viene aperta e nessuno fuori dalla tua rete Tailscale può raggiungerlo.

## 1. Installa Tailscale

- **PC (Windows):** `winget install -e --id Tailscale.Tailscale`, poi accedi dall'icona vicino all'orologio
- **Telefono:** app "Tailscale" da Play Store / App Store, **stesso account** del PC

## 2. Trova il nome del PC nella rete Tailscale

```powershell
tailscale status
```
La prima riga è il tuo PC: un indirizzo `100.x.y.z` e un nome. Con MagicDNS attivo (predefinito) il nome completo è del tipo `nome-pc.tail1234.ts.net`, visibile anche nella console di Tailscale.

## 3. Imposta l'indirizzo pubblico del Capo

Nel file `.env`:
```
CAPO_PUBLIC_URL=http://nome-pc.tail1234.ts.net:8100
```
Poi: `docker compose up -d --force-recreate capo`

Serve perché immagini e video siano visibili anche dal telefono (con `localhost` si vedrebbero solo dal PC).

## 4. Apri il Capo dal telefono

Con Tailscale attivo sul telefono: `http://nome-pc.tail1234.ts.net:3000`

Il PC deve essere acceso, con Docker e Ollama avviati.

## 5. Protezioni già attive

| Cosa | Protezione |
|---|---|
| Il Capo (porta 8100) | risponde solo con `CAPO_API_KEY`, che conosce solo Open WebUI |
| Pannello LiteLLM (porta 4000) | raggiungibile solo dal PC stesso |
| Open WebUI (porta 3000) | serve il tuo account; disattiva le nuove registrazioni (sotto) |

In Open WebUI: **Pannello di amministrazione → Impostazioni → Generale → Abilita nuove registrazioni: OFF**.

## 6. Backup

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\backup.ps1 -Destinazione "G:\Backup\neuralagora"
```
Ferma i servizi per qualche secondo, crea un archivio `.tar.gz` con chat, spesa, immagini/video, regole private e `.env`, poi riavvia. Tiene gli ultimi 8 backup.

Il backup si fa dentro Docker (con un piccolo container `alpine`), perché Windows da solo non riesce a leggere alcuni file creati dai container. La cache di Open WebUI è esclusa: si riscarica da sola.

Il backup contiene le tue chiavi: salvalo su un disco tuo, non in una cartella condivisa.

### Ripristino

1. `docker compose down`
2. Estrai l'archivio nella cartella del progetto (sovrascrive `data`, `output`, `private`, `.env`):
   ```powershell
   tar -xzf "G:\Backup\neuralagora\neuralagora_AAAA-MM-GG_HHMM.tar.gz" -C .
   ```
3. `docker compose up -d`
