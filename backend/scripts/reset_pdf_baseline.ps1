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

    & $python manage.py seed_pdf_baseline
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
