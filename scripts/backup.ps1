# ============================================================
#  Backup di Neural Agorà Control (Windows PowerShell)
#  Salva: chat e account (data\open-webui), spesa (data\postgres),
#         immagini e video generati (output) e il file .env.
#  Uso:   .\scripts\backup.ps1 -Destinazione "E:\Backup\neuralagora"
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

$data = Get-Date -Format "yyyy-MM-dd_HHmm"
New-Item -ItemType Directory -Force -Path $Destinazione | Out-Null
$archivio = Join-Path $Destinazione "neuralagora_$data.zip"

Write-Host "Fermo i servizi per una copia coerente..."
docker compose stop
try {
    $elementi = @(".env", "data", "output", "private") | Where-Object { Test-Path $_ }
    Compress-Archive -Path $elementi -DestinationPath $archivio -CompressionLevel Optimal
    Write-Host "Backup creato: $archivio"
}
finally {
    Write-Host "Riavvio i servizi..."
    docker compose start
}

# Tiene solo gli ultimi $Conserva backup
Get-ChildItem $Destinazione -Filter "neuralagora_*.zip" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -Skip $Conserva |
    Remove-Item -Force
Write-Host "Fatto. Backup conservati: $Conserva"
