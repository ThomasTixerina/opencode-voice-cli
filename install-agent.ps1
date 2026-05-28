<#
.SYNOPSIS
  Instala / desinstala el Voice Agent de OpenCode en Startup de Windows
.DESCRIPTION
  Crea un acceso directo en shell:startup para que voice-agent.pyw
  se ejecute automaticamente al iniciar Windows, en segundo plano.
.EXAMPLE
  .\install-agent.ps1 -Install
  .\install-agent.ps1 -Uninstall
  .\install-agent.ps1 -Status
#>

param(
  [ValidateSet("Install", "Uninstall", "Status")]
  [string]$Action = "Install"
)

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$AgentScript = Join-Path $ScriptDir "voice-agent.pyw"
$LogFile = "$env:USERPROFILE\.opencode\voice-agent.log"
$ShortcutDir = [Environment]::GetFolderPath("Startup")
$ShortcutPath = Join-Path $ShortcutDir "voice-agent.lnk"

function Install {
  if (-not (Test-Path $AgentScript)) {
    Write-Host "[ERROR] voice-agent.pyw no encontrado en $ScriptDir" -ForegroundColor Red
    exit 1
  }

  # Crear acceso directo en shell:startup
  $WScriptShell = New-Object -ComObject WScript.Shell
  $Shortcut = $WScriptShell.CreateShortcut($ShortcutPath)
  $Shortcut.TargetPath = "pythonw.exe"
  $Shortcut.Arguments = "`"$AgentScript`""
  $Shortcut.WorkingDirectory = "$env:USERPROFILE"
  $Shortcut.WindowStyle = 7  # Minimized
  $Shortcut.Description = "Voice Agent - OpenCode voice integration"
  $Shortcut.Save()

  # Crear tambien un .bat para matar facil
  $KillBat = Join-Path (Split-Path $ScriptDir) ".opencode\stop-agent.bat"
@"
@echo off
echo Deteniendo Voice Agent...
taskkill /f /im pythonw.exe >nul 2>&1
echo Voice Agent detenido.
pause
"@ | Out-File -FilePath $KillBat -Encoding ASCII

  Write-Host ""
  Write-Host "====================================" -ForegroundColor Cyan
  Write-Host "  Voice Agent INSTALADO" -ForegroundColor Green
  Write-Host "====================================" -ForegroundColor Cyan
  Write-Host ""
  Write-Host "Se ejecutara automaticamente al iniciar Windows." -ForegroundColor Yellow
  Write-Host "Para iniciarlo ahora, ejecuta:" -ForegroundColor Yellow
  Write-Host "  pythonw `"$AgentScript`"" -ForegroundColor White
  Write-Host ""
  Write-Host "Para detenerlo:" -ForegroundColor Yellow
  Write-Host "  $env:USERPROFILE\.opencode\stop-agent.bat" -ForegroundColor White
  Write-Host "  (o mata el proceso pythonw.exe)" -ForegroundColor Yellow
  Write-Host ""
  Write-Host "Logs: $LogFile" -ForegroundColor Gray
}

function Uninstall {
  if (Test-Path $ShortcutPath) {
    Remove-Item $ShortcutPath -Force
    Write-Host "[OK] Acceso directo eliminado de startup." -ForegroundColor Green
  } else {
    Write-Host "[INFO] No habia instalacion previa." -ForegroundColor Yellow
  }
}

function Status {
  $running = Get-Process pythonw -ErrorAction SilentlyContinue | Where-Object {
    $_.CommandLine -match "voice-agent"
  }
  $installed = Test-Path $ShortcutPath

  Write-Host ""
  Write-Host "=== Voice Agent Status ===" -ForegroundColor Cyan
  if ($installed) {
    Write-Host "  Startup:    INSTALADO (se inicia con Windows)" -ForegroundColor Green
  } else {
    Write-Host "  Startup:    NO INSTALADO" -ForegroundColor Yellow
  }
  if ($running) {
    Write-Host "  Estado:     EJECUTANDOSE" -ForegroundColor Green
    Write-Host "  PID:       $($running.Id)" -ForegroundColor Gray
  } else {
    Write-Host "  Estado:     DETENIDO" -ForegroundColor Yellow
  }
  if (Test-Path $LogFile) {
    Write-Host "  Log:        $LogFile" -ForegroundColor Gray
    Write-Host "  Ultimas lineas:" -ForegroundColor Gray
    Get-Content $LogFile -Tail 3
  }
  Write-Host ""
}

switch ($Action) {
  "Install"   { Install }
  "Uninstall" { Uninstall }
  "Status"    { Status }
}
