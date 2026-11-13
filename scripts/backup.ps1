# ============================================================
#  Backup di Neural Agorà Control (Windows PowerShell)
#  Salva: chat e account (data\open-webui, senza la cache),
#         spesa (data\postgres), immagini e video (output),
#         regole private (private) e il file .env.
#  Il backup si fa dentro Docker: legge anche i file creati
#  dai container, che Windows da solo non riesce ad aprire.
#
#  Uso:   powershell -ExecutionPolicy Bypass -File .\scripts\backup.ps1 -Destinazione "G:\Backup\neuralagora"
#  Attenzione: il backup contiene le tue chiavi (.env).
#  Tienilo su un disco tuo, non in una cartella condivisa.
# ============================================================
param(
    [Parameter(Mandatory = $true)][string]$Destinazione,
    [int]$Conserva = 8
)
$ErrorActionPreference = "Stop"
$progetto = Split-Path -Parent $PSScriptRoot
Set-Location $progetto

New-Item -ItemType Directory -Force -Path $Destinazione | Out-Null
$Destinazione = (Resolve-Path $Destinazione).Path
$nome = "neuralagora_$(Get-Date -Format 'yyyy-MM-dd_HHmm').tar.gz"

$elementi = @(".env", "data", "output", "private") | Where-Object { Test-Path $_ }

Write-Host "Fermo i servizi per una copia coerente..."
docker compose stop
try {
    docker run --rm `
        -v "${progetto}:/progetto:ro" `
        -v "${Destinazione}:/backup" `
        alpine tar -czf "/backup/$nome" -C /progetto `
        --exclude=data/open-webui/cache `
        @elementi
    if ($LASTEXITCODE -ne 0) { throw "La creazione del backup non è riuscita (codice $LASTEXITCODE)." }
    $dimensione = [math]::Round((Get-Item (Join-Path $Destinazione $nome)).Length / 1MB, 1)
    Write-Host "Backup creato: $(Join-Path $Destinazione $nome) ($dimensione MB)"
}
finally {
    Write-Host "Riavvio i servizi..."
    docker compose start
}

# Tiene solo gli ultimi $Conserva backup
Get-ChildItem $Destinazione -Filter "neuralagora_*.tar.gz" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -Skip $Conserva |
    Remove-Item -Force
Write-Host "Fatto. Backup conservati: al massimo $Conserva"
Write-Host "Per ripristinare: docs\ONLINE.md, sezione Backup."
