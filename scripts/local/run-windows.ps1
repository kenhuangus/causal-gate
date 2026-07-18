[CmdletBinding()]
param(
    [int]$Port = 8080,
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$RootDir = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$EnvFile = if ($env:CAUSALGATE_ENV_FILE) { $env:CAUSALGATE_ENV_FILE } else { Join-Path $RootDir ".causalgate.local.env" }
$env:CAUSALGATE_PORT = "$Port"

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker is required. Install and start Docker Desktop, then rerun this script."
}

docker compose version *> $null
if ($LASTEXITCODE -ne 0) {
    throw "Docker Compose v2 is required. Install or start Docker Desktop."
}

function New-HexSecret {
    $bytes = New-Object byte[] 32
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    return ([BitConverter]::ToString($bytes)).Replace("-", "").ToLowerInvariant()
}

if (-not (Test-Path $EnvFile)) {
    @(
        "CAUSALGATE_ATTESTATION_KEY=$(New-HexSecret)"
        "CAUSALGATE_GRANT_SIGNING_KEY=$(New-HexSecret)"
        "CAUSALGATE_LIVE_ANALYSIS_ENABLED=true"
        "CAUSALGATE_LIVE_ANALYSIS_LIMIT=3"
        "CAUSALGATE_PORT=$Port"
        "OPENAI_MODEL=gpt-5.6-sol"
    ) | Set-Content -Path $EnvFile -Encoding ascii
    Write-Host "Created local runtime secrets in $EnvFile"
}

Push-Location $RootDir
try {
    docker compose --env-file $EnvFile up --build --wait
    if ($LASTEXITCODE -ne 0) { throw "Docker Compose failed to start CausalGate." }
} finally {
    Pop-Location
}

$Url = "http://localhost:$Port"
$Healthy = $false
for ($Attempt = 0; $Attempt -lt 30; $Attempt++) {
    try {
        $Response = Invoke-WebRequest -UseBasicParsing -Uri "$Url/health" -TimeoutSec 2
        if ($Response.StatusCode -eq 200) { $Healthy = $true; break }
    } catch {
        Start-Sleep -Seconds 1
    }
}
if (-not $Healthy) { throw "CausalGate did not become healthy. Run: docker compose logs causalgate" }

Write-Host "CausalGate is ready at $Url"
Write-Host "The deterministic demo needs no API key. Enter a restricted OpenAI project key in the UI only for optional live analysis."
if (-not $NoBrowser) { Start-Process $Url }
