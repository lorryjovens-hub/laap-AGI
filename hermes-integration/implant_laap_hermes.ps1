#Requires -Version 5.1
<#
.SYNOPSIS
    一键将 LAAP 植入 Hermes Agent 并自动挂载。

.DESCRIPTION
    本脚本执行以下操作：
      1. 自动探测 LAAP 根目录与 Hermes 安装位置
      2. 将 LAAP MCP Server 写入 Hermes 的 config.yaml
      3. 可选：源码级注入 LAAP 认知状态到 Hermes system prompt
      4. 启动 LAAP Brain API 并等待 /health 就绪
      5. 启动 Hermes chat（默认使用 laap-bridge skill）

.PARAMETER Port
    LAAP Brain API 端口，默认 11546。

.PARAMETER NoSystemPromptPatch
    跳过 system_prompt.py 的源码级注入（仅使用 MCP 方式）。

.PARAMETER HermesHome
    显式指定 Hermes 安装目录。

.EXAMPLE
    .\implant_laap_hermes.ps1
    .\implant_laap_hermes.ps1 -Port 11547 -NoSystemPromptPatch
#>
param(
    [int]$Port = 11546,
    [switch]$NoSystemPromptPatch,
    [string]$HermesHome = ""
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

# ── 路径探测 ────────────────────────────────────────────────
$LAAP_ROOT = if ($env:LAAP_ROOT) { $env:LAAP_ROOT } else { (Resolve-Path "$PSScriptRoot\..").Path }
$ARIS_BRAIN = Join-Path $LAAP_ROOT "aris_brain"
$MCP_SERVER = Join-Path $LAAP_ROOT "mcp_server\laap_mcp_server.py"
$API_BASE = "http://localhost:$Port"

if (-not $HermesHome) {
    $HermesHome = if ($env:HERMES_HOME) { $env:HERMES_HOME } else { "$env:LOCALAPPDATA\hermes\hermes-agent" }
}
$HermesConfigDir = "$env:USERPROFILE\.hermes"
$HermesConfigFile = Join-Path $HermesConfigDir "config.yaml"
$SystemPromptFile = Join-Path $HermesHome "agent\system_prompt.py"
$BackupFile = "$SystemPromptFile.laap-backup"

function Test-Command($cmd) { return [bool](Get-Command $cmd -ErrorAction SilentlyContinue) }
function Write-Step($n, $total, $msg) { Write-Host "[$n/$total] $msg" -ForegroundColor Cyan }

Write-Host "============================================================" -ForegroundColor Blue
Write-Host " LAAP + Hermes 一键植入 / 自动挂载" -ForegroundColor Blue
Write-Host "============================================================" -ForegroundColor Blue
Write-Host "LAAP root:    $LAAP_ROOT"
Write-Host "Hermes home:  $HermesHome"
Write-Host "API base:     $API_BASE"
Write-Host ""

# ── 校验环境 ────────────────────────────────────────────────
if (-not (Test-Path $LAAP_ROOT)) { throw "LAAP root not found: $LAAP_ROOT" }
if (-not (Test-Path $MCP_SERVER)) { throw "LAAP MCP server not found: $MCP_SERVER" }
if (-not (Test-Command "python")) { throw "python not found in PATH" }
if (-not (Test-Command "hermes")) { Write-Warning "hermes not found in PATH; will try to use HERMES_HOME directly" }

# 探测 Hermes 虚拟环境 Python
$HermesVenvPython = "$HermesHome\venv\Scripts\python.exe"
if (-not (Test-Path $HermesVenvPython)) {
    $HermesVenvPython = (Get-Command python).Source
}

# ── 1. 写入 Hermes MCP 配置 ─────────────────────────────────
Write-Step 1 5 "Writing Hermes MCP config..."
New-Item -ItemType Directory -Force -Path $HermesConfigDir | Out-Null

$laapBlock = @"
# --- LAAP auto-implanted block (do not edit manually) ---
  laap_brain:
    command: "$($HermesVenvPython -replace '\\', '\\')"
    args:
      - "$($MCP_SERVER -replace '\\', '\\')"
    env:
      LAAP_API_BASE: "$API_BASE"
    timeout: 30
    connect_timeout: 10
    keepalive_interval: 60
# --- end LAAP block ---
"@

$configContent = ""
if (Test-Path $HermesConfigFile) {
    $configContent = Get-Content -Raw -Path $HermesConfigFile -Encoding utf8
} else {
    $configContent = "skills:`n  preload:`n    - laap-bridge`n"
}

# 移除旧 LAAP 块
$configContent = [regex]::Replace($configContent,
    "# --- LAAP auto-implanted block.*?# --- end LAAP block ---\r?\n?",
    "",
    [System.Text.RegularExpressions.RegexOptions]::Singleline)

# 注入新块
if ($configContent -match "^mcp_servers:\s*$") {
    $configContent = $configContent -replace "^(mcp_servers:\s*)$", "`$1`n$laapBlock"
} elseif ($configContent -match "mcp_servers:") {
    $configContent = $configContent -replace "(mcp_servers:.*?)(\n\S)", "`$1`n$laapBlock`$2"
} else {
    $configContent += "`nmcp_servers:`n$laapBlock`n"
}

# 确保 skills.preload 包含 laap-bridge
if ($configContent -notmatch "laap-bridge") {
    if ($configContent -match "skills:\s*\n") {
        $configContent = $configContent -replace "(skills:\s*\n)", "`$1  preload:`n    - laap-bridge`n"
    } else {
        $configContent += "`nskills:`n  preload:`n    - laap-bridge`n"
    }
}

Set-Content -Path $HermesConfigFile -Value $configContent -Encoding utf8
Write-Host "Hermes config updated: $HermesConfigFile" -ForegroundColor Green

# ── 2. 可选：源码级 system prompt 注入 ─────────────────────
if (-not $NoSystemPromptPatch -and (Test-Path $SystemPromptFile)) {
    Write-Step 2 5 "Patching Hermes system_prompt.py for LAAP state injection..."
    if (-not (Test-Path $BackupFile)) {
        Copy-Item -Path $SystemPromptFile -Destination $BackupFile -Force
        Write-Host "Backup created: $BackupFile" -ForegroundColor DarkGray
    }

    $code = Get-Content -Raw -Path $SystemPromptFile -Encoding utf8
    $injectMarker = "# --- LAAP PSI injection (auto-implanted) ---"
    if ($code -notcontains $injectMarker) {
        $snippet = @"

$injectMarker
import os, urllib.request, urllib.error, json
def _laap_psi_preamble(user_input: str = "") -> str:
    base = os.environ.get("LAAP_API_BASE", "$API_BASE")
    url = f"{base}/v1/cognitive_state"
    try:
        data = json.dumps({"input": user_input}).encode()
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=2) as resp:
            result = json.loads(resp.read().decode())
            return result.get("preamble", "")
    except Exception:
        return ""
# --- end LAAP PSI injection ---
"@
        $code += $snippet
        Set-Content -Path $SystemPromptFile -Value $code -Encoding utf8
        Write-Host "system_prompt.py patched." -ForegroundColor Green
    } else {
        Write-Host "system_prompt.py already contains LAAP marker, skipped." -ForegroundColor DarkYellow
    }
} else {
    Write-Step 2 5 "Skipping system_prompt.py patch (NoSystemPromptPatch or file not found)."
}

# ── 3. 启动 LAAP Brain API ──────────────────────────────────
Write-Step 3 5 "Starting LAAP Brain API on port $Port..."
$existing = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue | Select-Object -First 1
if ($existing) {
    Write-Warning "Port $Port already in use (PID $($existing.OwningProcess)); attempting to stop..."
    Stop-Process -Id $existing.OwningProcess -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 1
}

$laapProcess = Start-Process -FilePath "python" -ArgumentList "`"$ARIS_BRAIN\laap_brain_api.py`" --port $Port" -PassThru -WindowStyle Minimized

# ── 4. 等待 API 就绪 ────────────────────────────────────────
Write-Step 4 5 "Waiting for LAAP API /health ..."
$ready = $false
for ($i = 0; $i -lt 30; $i++) {
    try {
        $resp = Invoke-WebRequest -Uri "$API_BASE/health" -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
        if ($resp.StatusCode -eq 200) {
            $ready = $true
            break
        }
    } catch { }
    Start-Sleep -Seconds 1
}
if (-not $ready) {
    if ($laapProcess -and -not $laapProcess.HasExited) { $laapProcess.Kill() }
    throw "LAAP API failed to start within 30 seconds. Check $ARIS_BRAIN\laap_brain_api.py"
}
Write-Host "LAAP API is ready at $API_BASE/health" -ForegroundColor Green

# ── 5. 启动 Hermes chat ─────────────────────────────────────
Write-Step 5 5 "Launching Hermes chat with laap-bridge skill..."
$env:LAAP_API_BASE = $API_BASE

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host " LAAP is now mounted to Hermes." -ForegroundColor Green
Write-Host " Type your message in the Hermes chat window." -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green

if (Test-Command "hermes") {
    Start-Process -FilePath "hermes" -ArgumentList "chat --skills laap-bridge" -Wait
} else {
    $hermesCli = "$HermesHome\venv\Scripts\hermes.exe"
    if (Test-Path $hermesCli) {
        Start-Process -FilePath $hermesCli -ArgumentList "chat --skills laap-bridge" -Wait
    } else {
        Write-Warning "Cannot locate hermes executable; please run manually: hermes chat --skills laap-bridge"
        Read-Host "Press Enter to stop LAAP API and exit"
    }
}

# ── 清理 ────────────────────────────────────────────────────
if ($laapProcess -and -not $laapProcess.HasExited) {
    $laapProcess.Kill()
    Write-Host "LAAP API stopped." -ForegroundColor DarkGray
}
