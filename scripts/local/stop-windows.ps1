[CmdletBinding()]
param([switch]$RemoveData)

$ErrorActionPreference = "Stop"
$RootDir = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$EnvFile = if ($env:CAUSALGATE_ENV_FILE) { $env:CAUSALGATE_ENV_FILE } else { Join-Path $RootDir ".causalgate.local.env" }

if (-not (Test-Path $EnvFile)) { throw "No local CausalGate environment was found at $EnvFile" }

Push-Location $RootDir
try {
    if ($RemoveData) {
        docker compose --env-file $EnvFile down --volumes
        Write-Host "CausalGate stopped and its local Docker volume was removed."
    } else {
        docker compose --env-file $EnvFile down
        Write-Host "CausalGate stopped. Local demo data was preserved."
    }
    if ($LASTEXITCODE -ne 0) { throw "Docker Compose failed to stop CausalGate." }
} finally {
    Pop-Location
}
