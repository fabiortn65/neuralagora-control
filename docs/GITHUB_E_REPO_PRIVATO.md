# Pubblicare su GitHub: repo pubblico + repo privato

Il progetto vive in due repository:

| Repo | Visibilità | Contenuto |
|---|---|---|
| `neuralagora-control` | Pubblico | il motore, uguale per tutti |
| `neuralagora-control-private` | Privato | le tue regole, prompt, workflow e integrazioni personali |

> GitHub non permette un fork privato di un repo pubblico: per questo il privato si crea come repo separato che riceve gli aggiornamenti dal pubblico.

## Passo 1 — Crea il repo pubblico

1. Su GitHub: **New repository**
2. Nome: `neuralagora-control`, visibilità **Public**
3. **Non** aggiungere README, licenza o .gitignore (li hai già)
4. Dal tuo PC, nella cartella del progetto:

```bash
git init
git add .
git commit -m "Prima versione di Neural Agorà Control"
git branch -M main
git remote add origin https://github.com/<tuo-utente>/neuralagora-control.git
git push -u origin main
```

5. Nelle impostazioni del repo: **Settings → Code security** → attiva **Secret scanning** e **Push protection**. GitHub bloccherà i push che contengono chiavi API.

## Passo 2 — Crea il repo privato

1. Su GitHub: **New repository**, nome `neuralagora-control-private`, visibilità **Private**, vuoto
2. Dal tuo PC, in una cartella diversa:

```bash
git clone https://github.com/<tuo-utente>/neuralagora-control.git neuralagora-control-private
cd neuralagora-control-private
git remote rename origin upstream
git remote add origin https://github.com/<tuo-utente>/neuralagora-control-private.git
git push -u origin main
```

Adesso il privato ha due collegamenti:
- `origin`: il tuo repo privato (dove salvi le tue modifiche)
- `upstream`: il repo pubblico (da cui ricevi gli aggiornamenti del motore)

## Passo 3 — Personalizza il privato

Le personalizzazioni vanno in una cartella che nel pubblico non esiste, così gli aggiornamenti non creano conflitti:

```
private/
  rules.yaml          le tue regole del Capo
  workflows/          i tuoi workflow ComfyUI
  docker-compose.override.yml
```

> Nel pubblico `private/` è esclusa dal `.gitignore`. Nel repo privato invece va salvata: togli la riga `private/` dal `.gitignore` **solo nel privato**.

Esempio di `docker-compose.override.yml` nel privato, che Docker legge in automatico:

```yaml
services:
  capo:
    volumes:
      - ./private/rules.yaml:/app/rules.yaml:ro
      - ./private/workflows:/app/workflows:ro
```

## Passo 4 — Ricevere gli aggiornamenti dal pubblico

Quando migliori il motore, lavora nel **pubblico**. Poi, nel privato:

```bash
git pull upstream main
git push origin main
```

## Regola d'oro

Una modifica utile a tutti → repo pubblico.
Una modifica che riguarda solo te → cartella `private/` nel repo privato.
Le chiavi → **solo** nel file `.env`, mai in nessun repo.
