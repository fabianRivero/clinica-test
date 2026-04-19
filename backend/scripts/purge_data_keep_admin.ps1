param(
    [string[]]$Username = @("admin"),
    [switch]$Force
)

$ErrorActionPreference = "Stop"

$backendRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$workspaceRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$pythonExe = Join-Path $workspaceRoot "env\Scripts\python.exe"

if (-not (Test-Path $pythonExe)) {
    throw "No se encontro el entorno virtual en $pythonExe"
}

$arguments = @("manage.py", "purge_data_keep_admin")
foreach ($item in $Username) {
    $arguments += @("--username", $item)
}
if ($Force) {
    $arguments += "--force"
}

Push-Location $backendRoot
try {
    & $pythonExe @arguments
}
finally {
    Pop-Location
}
