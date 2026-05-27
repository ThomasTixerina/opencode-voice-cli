#!/usr/bin/env pwsh
<#
.SYNOPSIS
  Voice CLI — Habla con OpenCode AI
.DESCRIPTION
  Wrapper para voice-cli.py y voice-agent.pyw.
  Usa Groq Whisper (STT) + edge-tts (TTS) + SendKeys.
.PARAMETER Record
  Graba voz y transcribe
.PARAMETER Speak
  Lee texto en voz alta
.PARAMETER Hear
  Lee el portapapeles
.PARAMETER Listen
  Modo wake word + auto-type
.PARAMETER Watch
  Vigila archivo y lee cambios
.PARAMETER AutoType
  Auto-escritura en terminal activa
.PARAMETER Duration
  Duracion de grabacion en segundos
.PARAMETER Voice
  Voz TTS
.PARAMETER Agent
  Inicia agente de fondo
.PARAMETER Install
  Instala en Windows startup
.PARAMETER Uninstall
  Desinstala de startup
.PARAMETER Status
  Muestra estado
#>

param(
  [switch]$Record,
  [string]$Speak,
  [switch]$Hear,
  [switch]$Listen,
  [string]$Watch,
  [switch]$AutoType,
  [float]$Duration = 5,
  [string]$Voice = "es-MX-JorgeNeural",
  [switch]$Agent,
  [switch]$Install,
  [switch]$Uninstall,
  [switch]$Status
)

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$CLI = Join-Path $ScriptDir "voice-cli.py"
$AgentScript = Join-Path $ScriptDir "voice-agent.pyw"
$Installer = Join-Path $ScriptDir "install-agent.ps1"

if ($Install) {
  & $Installer -Install
  return
}

if ($Uninstall) {
  & $Installer -Uninstall
  return
}

if ($Status) {
  & $Installer -Status
  return
}

if ($Agent) {
  if (-not (Test-Path $AgentScript)) {
    Write-Error "voice-agent.pyw no encontrado"
    exit 1
  }
  Write-Host "Iniciando Voice Agent..." -ForegroundColor Cyan
  Start-Process pythonw -ArgumentList "`"$AgentScript`""
  return
}

if (-not (Test-Path $CLI)) {
  Write-Error "voice-cli.py no encontrado"
  exit 1
}

$argsList = @()
if ($Record) { $argsList += "--record" }
if ($Speak)  { $argsList += "--speak"; $argsList += $Speak }
if ($Hear)   { $argsList += "--hear" }
if ($Listen) { $argsList += "--listen" }
if ($Watch)  { $argsList += "--watch"; $argsList += $Watch }
if ($AutoType) { $argsList += "--auto-type" }
$argsList += "--duration"; $argsList += "$Duration"
$argsList += "--voice"; $argsList += $Voice

python $CLI @argsList
