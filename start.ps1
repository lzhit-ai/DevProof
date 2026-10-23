[CmdletBinding()]
param(
    [switch]$Rebuild,
    [switch]$Refactor,
    [switch]$HandoffAlembic
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repoRoot = $PSScriptRoot
$composeFile = Join-Path $repoRoot "infra/docker-compose.refactor.yml"
$composeFiles = @("-f", $composeFile)
$environmentFile = Join-Path $repoRoot "infra/.env"
$composeProject = Split-Path (Split-Path $composeFile -Parent) -Leaf
$postgresDataVolume = "${composeProject}_postgres-data"

function New-LocalSecret {
    param([int]$ByteLength, [switch]$Base64)

    $bytes = New-Object byte[] $ByteLength
    $random = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $random.GetBytes($bytes)
    }
    finally {
        $random.Dispose()
    }

    if ($Base64) { return [Convert]::ToBase64String($bytes) }
    return (($bytes | ForEach-Object { $_.ToString("x2") }) -join "")
}

function Invoke-Compose {
    param([string[]]$ComposeArguments)

    & docker compose --env-file $environmentFile @composeFiles @ComposeArguments
    if ($LASTEXITCODE -ne 0) {
        throw "Docker Compose failed: docker compose $($ComposeArguments -join ' ')"
    }
}

function Wait-ForApiReady {
    $deadline = (Get-Date).AddSeconds(120)
    $readyUrl = "http://localhost:8080/api/v1/health/ready"

    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest -Uri $readyUrl -UseBasicParsing -TimeoutSec 5
            if ($response.StatusCode -eq 200) {
                return
            }
        }
        catch {
            # 服务仍在启动中。
        }
        Start-Sleep -Seconds 2
    }

    throw "API did not become ready within 120 seconds. Run: docker compose --env-file infra/.env -f infra/docker-compose.refactor.yml logs business gateway"
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker was not found. Install and start Docker Desktop first."
}

& docker info *> $null
if ($LASTEXITCODE -ne 0) {
    throw "Docker Engine is not running. Start Docker Desktop and try again."
}

& docker compose version *> $null
if ($LASTEXITCODE -ne 0) {
    throw "Docker Compose V2 is unavailable. Upgrade Docker Desktop and try again."
}

if (-not (Test-Path -LiteralPath $environmentFile)) {
    & docker volume inspect $postgresDataVolume *> $null
    if ($LASTEXITCODE -eq 0) {
        throw "Existing PostgreSQL data volume '$postgresDataVolume' was found, but infra/.env is missing. Restore the original POSTGRES_PASSWORD in infra/.env or remove that volume only when its data can be discarded."
    }

    $postgresPassword = New-LocalSecret -ByteLength 24
    $jwtSecret = New-LocalSecret -ByteLength 48
    @"
# 由 start.ps1 为本地开发生成。请勿将此文件提交到 git。
POSTGRES_DB=ai_codereview
POSTGRES_USER=ai_codereview
POSTGRES_PASSWORD=$postgresPassword
JWT_SECRET=$jwtSecret
GENERATION_PROVIDER=deepseek
GENERATION_MODEL=deepseek-v4-flash
GENERATION_BASE_URL=https://api.deepseek.com
EMBEDDING_PROVIDER=dashscope
EMBEDDING_MODEL=text-embedding-v4
EMBEDDING_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
EMBEDDING_DIMENSIONS=768
# 在线 MinerU 文档解析（替代本地）。解析二进制文档（PDF、Office、图片）
# 时必须配置 MINERU_API_TOKEN，在 https://mineru.net 创建。
# MINERU_API_TOKEN=replace-with-your-mineru-api-token
"@ | Set-Content -LiteralPath $environmentFile -Encoding utf8
    Write-Host "Generated local configuration: infra/.env"
}

& {
    $localLines = Get-Content -LiteralPath $environmentFile
    $modelKeyLine = $localLines | Where-Object { $_ -match '^MODEL_CREDENTIAL_ENCRYPTION_KEY=' } | Select-Object -Last 1
    $modelKeyValue = if ($modelKeyLine) { ($modelKeyLine -split '=', 2)[1].Trim().Trim([char]34).Trim([char]39) } else { "" }
    if ([string]::IsNullOrWhiteSpace($modelKeyValue)) {
        $modelEncryptionKey = New-LocalSecret -ByteLength 32 -Base64
        if ($modelKeyLine) {
            $localLines = $localLines | ForEach-Object { if ($_ -match '^MODEL_CREDENTIAL_ENCRYPTION_KEY=') { "MODEL_CREDENTIAL_ENCRYPTION_KEY=$modelEncryptionKey" } else { $_ } }
            Set-Content -LiteralPath $environmentFile -Encoding utf8 -Value $localLines
        } else { Add-Content -LiteralPath $environmentFile -Encoding utf8 -Value @("", "MODEL_CREDENTIAL_ENCRYPTION_KEY=$modelEncryptionKey") }
        Write-Host "Configured dedicated personal model credential encryption in infra/.env."
    }
    $hasWorkerToken = [bool]($localLines | Where-Object { $_ -match '^AGENT_SERVICE_TOKEN=' })
    $hasWorkerCredentials = [bool]($localLines | Where-Object { $_ -match '^AGENT_WORKER_CREDENTIALS=' })
    if (-not $hasWorkerToken -and -not $hasWorkerCredentials) {
        $workerIdentity = "agent-worker-local"
        $identityLine = $localLines | Where-Object { $_ -match '^AGENT_WORKER_ID=' } | Select-Object -Last 1
        if ($identityLine) { $workerIdentity = ($identityLine -split '=', 2)[1].Trim().Trim([char]34).Trim([char]39) }
        if ($workerIdentity -notmatch '^[A-Za-z0-9._-]{1,160}$') { throw "Invalid AGENT_WORKER_ID." }
        $workerSecret = New-LocalSecret -ByteLength 32
        $workerCredentialMap = @{ $workerIdentity = $workerSecret } | ConvertTo-Json -Compress
        Add-Content -LiteralPath $environmentFile -Encoding utf8 -Value @("", "AGENT_WORKER_ID=$workerIdentity", "AGENT_SERVICE_TOKEN=$workerSecret", "AGENT_WORKER_CREDENTIALS=$workerCredentialMap")
        Write-Host "Configured local Worker identity credentials in infra/.env."
    }
    elseif (-not $hasWorkerToken -or -not $hasWorkerCredentials) {
        throw "Configure both AGENT_SERVICE_TOKEN and AGENT_WORKER_CREDENTIALS in infra/.env; the Worker identity and token must match."
    }
    $computeLine = $localLines | Where-Object { $_ -match '^COMPUTE_SERVICE_TOKEN=' } | Select-Object -Last 1
    if (-not $computeLine) {
        $computeSecret = New-LocalSecret -ByteLength 32
        Add-Content -LiteralPath $environmentFile -Encoding utf8 -Value @("", "COMPUTE_SERVICE_TOKEN=$computeSecret")
        Write-Host "Configured internal computation credentials in infra/.env."
    }
}

Write-Host "Stopping legacy business processes..."
& docker compose --env-file $environmentFile -f (Join-Path $repoRoot "infra/docker-compose.yml") stop api worker
if ($LASTEXITCODE -ne 0) { throw "Could not stop this project's legacy API/Worker." }

Write-Host "Starting PostgreSQL and Redis..."
Invoke-Compose -ComposeArguments @("up", "-d", "postgres", "redis")

Write-Host "Running Java schema migration..."
$migrationMode = "migrate"
if ($HandoffAlembic) { $migrationMode = "handoff-alembic" }
$migrationArguments = @("run", "--rm")
if ($Rebuild) { $migrationArguments += "--build" }
Invoke-Compose -ComposeArguments ($migrationArguments + @("migrate", "db", $migrationMode))

Write-Host "Starting business, Agent, gateway and frontend..."
$applicationArguments = @("up", "-d")
if ($Rebuild) { $applicationArguments += "--build" }
Invoke-Compose -ComposeArguments ($applicationArguments + @("business", "agent-worker", "gateway", "frontend"))

Write-Host "Waiting for business gateway readiness..."
Wait-ForApiReady
Write-Host "Startup complete."
Write-Host "Frontend: http://localhost:5173"
Write-Host "Business API: http://localhost:8080/api/v1"
Write-Host "Create your account using the registration page, or sign in with an existing account."
