param([switch]$Stop,[switch]$Restart,[switch]$Status)
$ROOT  = Split-Path -Parent $MyInvocation.MyCommand.Definition
$BACK  = Join-Path $ROOT "RagBackend"
$FRONT = Join-Path $ROOT "RagFrontend"
$ENV_FILE = Join-Path $BACK ".env"
$LOCAL_MYSQL_CNF = Join-Path $ROOT ".local-mysql\my-3307.cnf"
$BACKEND_PORT_FILE = Join-Path $ROOT ".dev-backend-port"
$BackendPort = 8000

function Test-Port { param([int]$p); $r = netstat -ano 2>$null | Select-String (":$p\s") | Select-String "LISTENING"; return ($null -ne $r -and $r.Count -gt 0) }
function Get-PidOnPort { param([int]$p); $line = netstat -ano 2>$null | Select-String (":$p\s") | Select-String "LISTENING" | Select-Object -First 1; if ($line) { return (($line.Line -split "\s+") | Where-Object { $_ -ne "" } | Select-Object -Last 1) }; return $null }
function Get-FrontPort { if (Test-Port 5173) { return 5173 } elseif (Test-Port 5174) { return 5174 } else { return 0 } }
function Test-BackendHealthy {
  param([string]$BaseUrl = "http://localhost:8000")
  try {
    $r = Invoke-WebRequest -Uri "$BaseUrl/api/RAG/health" -UseBasicParsing -TimeoutSec 4
    return ($r.StatusCode -ge 200 -and $r.StatusCode -lt 500)
  } catch {
    return $false
  }
}
function Get-LastBackendPort {
  if (Test-Path $BACKEND_PORT_FILE) {
    try {
      $v = [int](Get-Content $BACKEND_PORT_FILE -TotalCount 1)
      if ($v -gt 0) { return $v }
    } catch {}
  }
  return 8000
}
function Set-LastBackendPort { param([int]$Port)
  try { Set-Content -Path $BACKEND_PORT_FILE -Value $Port -Encoding ASCII } catch {}
}

function Get-EnvValue {
  param([string]$Key, [string]$Default = "")
  if (-not (Test-Path $ENV_FILE)) { return $Default }
  $line = Get-Content $ENV_FILE | Where-Object { $_ -match "^$Key=" } | Select-Object -First 1
  if (-not $line) { return $Default }
  return $line.Substring($Key.Length + 1)
}

$DB_HOST = Get-EnvValue "DB_HOST" "127.0.0.1"
$DB_PORT = [int](Get-EnvValue "DB_PORT" "3306")
$DB_USER = Get-EnvValue "DB_USER" "root"
$DB_PASSWORD = Get-EnvValue "DB_PASSWORD" ""

function Get-ProjectLocalMySQLPids {
    if (-not (Test-Path $LOCAL_MYSQL_CNF)) { return @() }
    $cnfRegex = [regex]::Escape($LOCAL_MYSQL_CNF)
    $procs = Get-CimInstance Win32_Process -Filter "Name='mysqld.exe'" -ErrorAction SilentlyContinue |
      Where-Object { $_.CommandLine -and $_.CommandLine -match $cnfRegex } |
      Select-Object -ExpandProperty ProcessId
    if ($null -eq $procs) { return @() }
    return @($procs)
}

function Test-DockerMySQL {
    $dockerReady = docker ps --format "{{.Names}}" 2>$null
    if (-not $dockerReady) { return $false }
    if (-not ($dockerReady -match "ragf-mysql")) { return $false }
    $result = docker exec ragf-mysql sh -c "MYSQL_PWD=$DB_PASSWORD mysql -u$DB_USER -e 'SELECT 1;'" 2>&1
    return ($result -match "1")
}

function Test-LocalMySQL {
    if (-not (Test-Port $DB_PORT)) { return $false }
    $mysqlCmd = Get-Command mysql -ErrorAction SilentlyContinue
    if ($mysqlCmd) {
      & $mysqlCmd.Source --host=$DB_HOST --port=$DB_PORT --user=$DB_USER --password=$DB_PASSWORD -e "SELECT 1;" 1>$null 2>$null
      if ($LASTEXITCODE -eq 0) { return $true }
    }

    $py = if (Get-Command python -ErrorAction SilentlyContinue) { "python" } elseif (Get-Command python3 -ErrorAction SilentlyContinue) { "python3" } else { return $false }
    $code = @"
import os
import pymysql
try:
    conn = pymysql.connect(
        host=os.environ['DB_HOST'],
        port=int(os.environ['DB_PORT']),
        user=os.environ['DB_USER'],
        password=os.environ['DB_PASSWORD'],
        connect_timeout=3,
    )
    with conn.cursor() as cur:
        cur.execute('SELECT 1')
        print('OK')
    conn.close()
except Exception:
    pass
"@
    $result = $code | & $py
    return ($result -match "OK")
}

function Start-ProjectLocalMySQL {
    # Built-in project local MySQL is configured on port 3307.
    if ($DB_PORT -ne 3307) { return $false }
    if (-not (Test-Path $LOCAL_MYSQL_CNF)) { return $false }
    $mysqldCmd = Get-Command mysqld -ErrorAction SilentlyContinue
    if (-not $mysqldCmd) { return $false }
    if (Test-LocalMySQL) { return $true }
    if ((Get-ProjectLocalMySQLPids).Count -gt 0 -and (Test-Port 3307)) {
      Start-Sleep 1
      if (Test-LocalMySQL) { return $true }
    }
    try {
      Start-Process -FilePath $mysqldCmd.Source -ArgumentList "--defaults-file=$LOCAL_MYSQL_CNF" -WindowStyle Hidden | Out-Null
    } catch {
      return $false
    }
    $w = 0
    while (-not (Test-LocalMySQL) -and $w -lt 20) { Start-Sleep 1; $w++ }
    return (Test-LocalMySQL)
}

if ($Status) {
  Write-Host "--- Status ---" -ForegroundColor Magenta
  $statusBackendPort = Get-LastBackendPort
  if (Test-DockerMySQL) {
    Write-Host "  [OK] MySQL (Docker ragf-mysql)" -ForegroundColor Green
  } elseif (Test-LocalMySQL) {
    Write-Host "  [OK] MySQL (Local ${DB_HOST}:${DB_PORT})" -ForegroundColor Green
  } else {
    Write-Host "  [X]  MySQL (Docker/Local not responding)" -ForegroundColor Red
  }
  $candidatePorts = @($statusBackendPort, 8000, 18000, 18001, 18002) | Select-Object -Unique
  $activePort = $null
  foreach ($cp in $candidatePorts) {
    if ((Test-Port $cp) -and (Test-BackendHealthy "http://localhost:$cp")) { $activePort = $cp; break }
  }
  if ($activePort) {
    Write-Host "  [OK] Backend  http://localhost:$activePort/docs" -ForegroundColor Green
  } elseif (Test-Port $statusBackendPort) {
    Write-Host "  [X]  Backend unhealthy (port $statusBackendPort occupied but API not responding)" -ForegroundColor Red
  } else {
    Write-Host "  [X]  Backend" -ForegroundColor Red
  }
  $fp = Get-FrontPort; if ($fp -gt 0) { Write-Host "  [OK] Frontend http://localhost:$fp" -ForegroundColor Green } else { Write-Host "  [X]  Frontend" -ForegroundColor Red }
  if (Test-Port 11434) { Write-Host "  [OK] Ollama" -ForegroundColor Green } else { Write-Host "  [--] Ollama not running (optional)" -ForegroundColor Yellow }
  exit 0
}

if ($Stop) {
  $p5 = Get-PidOnPort 5173; if ($p5) { taskkill /PID $p5 /F | Out-Null; Write-Host "Stopped frontend(5173)" -ForegroundColor Green }
  $p5b = Get-PidOnPort 5174; if ($p5b) { taskkill /PID $p5b /F | Out-Null; Write-Host "Stopped frontend(5174)" -ForegroundColor Green }
  $backendPorts = @(8000, (Get-LastBackendPort), 18000, 18001, 18002) | Select-Object -Unique
  foreach ($bp in $backendPorts) {
    $bpPid = Get-PidOnPort $bp
    if ($bpPid) {
      taskkill /PID $bpPid /F | Out-Null
      Write-Host "Stopped backend($bp)" -ForegroundColor Green
    }
  }
  foreach ($procId in Get-ProjectLocalMySQLPids) {
    taskkill /PID $procId /F | Out-Null
    Write-Host "Stopped local project MySQL(pid=$procId)" -ForegroundColor Green
  }
  Write-Host "Note: Docker MySQL (ragf-mysql) is managed by Docker, use 'docker compose stop' to stop it." -ForegroundColor Yellow
  exit 0
}

if ($Restart) { & $MyInvocation.MyCommand.Definition -Stop; Start-Sleep 2 }

Write-Host "=== KnowledgeRAG Quick Start ===" -ForegroundColor Cyan

Write-Host "[1/3] MySQL (Docker or Local)"
$mysqlReady = $false

if (Test-DockerMySQL) {
  Write-Host "  [OK] Docker MySQL ready (ragf-mysql)" -ForegroundColor Green
  $mysqlReady = $true
} elseif (Test-LocalMySQL) {
  Write-Host "  [OK] Local MySQL ready (${DB_HOST}:${DB_PORT})" -ForegroundColor Green
  $mysqlReady = $true
} elseif (Start-ProjectLocalMySQL) {
  Write-Host "  [OK] Project local MySQL started (.local-mysql on 127.0.0.1:3307)" -ForegroundColor Green
  $mysqlReady = $true
} else {
  Write-Host "  [!] MySQL not ready, trying Docker service mysql..." -ForegroundColor Yellow
  Push-Location $ROOT
  docker compose up -d mysql 2>&1 | Out-Null
  Pop-Location
  $w = 0
  while (-not (Test-DockerMySQL) -and -not (Test-LocalMySQL) -and $w -lt 30) { Start-Sleep 1; $w++ }
  if (Test-DockerMySQL) {
    Write-Host "  [OK] Docker MySQL ready (ragf-mysql)" -ForegroundColor Green
    $mysqlReady = $true
  } elseif (Test-LocalMySQL) {
    Write-Host "  [OK] Local MySQL ready (${DB_HOST}:${DB_PORT})" -ForegroundColor Green
    $mysqlReady = $true
  } elseif (Start-ProjectLocalMySQL) {
    Write-Host "  [OK] Project local MySQL started (.local-mysql on 127.0.0.1:3307)" -ForegroundColor Green
    $mysqlReady = $true
  }
}

if (-not $mysqlReady) {
  Write-Host "  [X] MySQL not responding. Please ensure either:" -ForegroundColor Red
  Write-Host "      1) Docker MySQL is up: docker compose up -d mysql" -ForegroundColor Red
  Write-Host "      2) Local MySQL matches .env (${DB_HOST}:${DB_PORT} $DB_USER)" -ForegroundColor Red
  exit 1
}

Write-Host "[2/3] Backend"
$py = if (Get-Command python -ErrorAction SilentlyContinue) { "python" } elseif (Get-Command python3 -ErrorAction SilentlyContinue) { "python3" } else { $null }
if (-not $py) { Write-Host "  [X] python not found" -ForegroundColor Red; exit 1 }

function Start-BackendOnPort {
  param([int]$Port)
  if (-not (Test-Port $Port)) {
    Start-Process -FilePath $py -ArgumentList "-m","uvicorn","main:app","--host","0.0.0.0","--port","$Port","--reload" -WorkingDirectory $BACK -WindowStyle Minimized
    $w = 0
    while (-not (Test-Port $Port) -and $w -lt 20) { Start-Sleep 1; $w++ }
  }
  if (Test-Port $Port) {
    $w = 0
    while (-not (Test-BackendHealthy "http://localhost:$Port") -and $w -lt 20) { Start-Sleep 1; $w++ }
    return (Test-BackendHealthy "http://localhost:$Port")
  }
  return $false
}

if ((Test-Port 8000) -and (Test-BackendHealthy "http://localhost:8000")) {
  $BackendPort = 8000
  Write-Host "  [skip] already running on 8000" -ForegroundColor Cyan
} else {
  if (Test-Port 8000) {
    Write-Host "  [!] port 8000 occupied but unhealthy, trying to restart..." -ForegroundColor Yellow
    $stalePid = Get-PidOnPort 8000
    if ($stalePid) {
      taskkill /PID $stalePid /F | Out-Null
      Start-Sleep 1
    }
  }

  if (Start-BackendOnPort 8000) {
    $BackendPort = 8000
  } else {
    $fallbackPorts = @(18000, 18001, 18002)
    $started = $false
    foreach ($p in $fallbackPorts) {
      if (Start-BackendOnPort $p) {
        $BackendPort = $p
        $started = $true
        break
      }
    }
    if (-not $started) {
      Write-Host "  [X] backend failed to start on 8000/18000/18001/18002" -ForegroundColor Red
      exit 1
    }
  }
}

Set-LastBackendPort $BackendPort
Write-Host "  [OK] http://localhost:$BackendPort/docs" -ForegroundColor Green

Write-Host "[3/3] Frontend (Vite)"
$efp = Get-FrontPort
if ($efp -gt 0 -and $BackendPort -eq 8000) {
  Write-Host "  [skip] already on port $efp" -ForegroundColor Cyan
} else {
  if ($efp -gt 0 -and $BackendPort -ne 8000) {
    $p5 = Get-PidOnPort 5173; if ($p5) { taskkill /PID $p5 /F | Out-Null }
    $p5b = Get-PidOnPort 5174; if ($p5b) { taskkill /PID $p5b /F | Out-Null }
    Start-Sleep 1
    Write-Host "  [i] restarted frontend to bind API => http://localhost:$BackendPort" -ForegroundColor Yellow
  }
  $narg = "/k cd /d `"$FRONT`" && set VITE_API_BASE_URL=http://localhost:$BackendPort && npm run dev"
  Start-Process cmd.exe -ArgumentList $narg -WindowStyle Normal
  $w=0; Write-Host "  waiting" -NoNewline
  while ((Get-FrontPort) -eq 0 -and $w -lt 35) { Start-Sleep 1; $w++; Write-Host "." -NoNewline }
  Write-Host ""
  $rfp = Get-FrontPort
  if ($rfp -gt 0) { Write-Host "  [OK] http://localhost:$rfp" -ForegroundColor Green } else { Write-Host "  [check Vite window - it may take longer]" -ForegroundColor Yellow }
}

Write-Host ""
Write-Host "=== All ready! ===" -ForegroundColor Green
Write-Host "  Backend:  http://localhost:$BackendPort" -ForegroundColor Green
Write-Host "  API Docs: http://localhost:$BackendPort/docs" -ForegroundColor Green
$ffp = Get-FrontPort; if ($ffp -gt 0) { Write-Host "  Frontend: http://localhost:$ffp" -ForegroundColor Green; Start-Process "http://localhost:$ffp" } else { Write-Host "  Frontend: check Vite window (5173 or 5174)" -ForegroundColor Yellow }
Write-Host ""
Write-Host "  [DB] Active DB target from .env: ${DB_HOST}:${DB_PORT} (user=$DB_USER)" -ForegroundColor Cyan
Write-Host "  [FE] VITE_API_BASE_URL=http://localhost:$BackendPort" -ForegroundColor Cyan
