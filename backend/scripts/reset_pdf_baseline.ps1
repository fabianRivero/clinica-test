param(
    [string[]]$Username = @("admin"),
    [switch]$Force
)

$ErrorActionPreference = "Stop"

$backendRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $backendRoot "env\\Scripts\\python.exe"

if (-not (Test-Path $python)) {
    throw "No se encontro Python del entorno virtual en $python"
}

Push-Location $backendRoot
try {
    Write-Host "[reset_pdf_baseline] Iniciando purge conservando administradores..." -ForegroundColor Cyan
    $purgeArgs = @("manage.py", "purge_data_keep_admin")
    foreach ($name in $Username) {
        $purgeArgs += "--username"
        $purgeArgs += $name
    }
    if ($Force) {
        $purgeArgs += "--force"
    }

    & $python @purgeArgs
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }

    Write-Host "[reset_pdf_baseline] Purge completado. Iniciando seed base PDF..." -ForegroundColor Green
    & $python manage.py seed_pdf_baseline
    if ($LASTEXITCODE -eq 0) {
        Write-Host "[reset_pdf_baseline] Seed completado correctamente." -ForegroundColor Green
        Write-Host "[reset_pdf_baseline] Revisa arriba las credenciales de tablet kiosko generadas para pruebas." -ForegroundColor Cyan
    }
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
