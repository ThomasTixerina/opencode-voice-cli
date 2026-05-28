#!/usr/bin/env pwsh
<#
.SYNOPSIS
  Voice CLI \u2014 Habla con OpenCode AI
.DESCRIPTION
  Wrapper para voice-cli.py y voice-agent.pyw.
  Usa Groq Whisper (STT) + edge-tts (TTS) + SendKeys.
.PARAMETER Record
  Graba voz y transcribe a texto (copiado al portapapeles)
.PARAMETER Speak
  Lee texto en voz alta
.PARAMETER Hear
  Lee el portapapeles en voz alta
.PARAMETER Listen
  [Fase2] Modo wake word: escucha "oye open..." y auto-escribe
.PARAMETER Watch
  Vigila un archivo y lee cambios en voz alta
.PARAMETER AutoType
  Auto-escritura en terminal activa (con --listen)
.PARAMETER Duration
  Duracion de grabacion en segundos (default: 5)
.PARAMETER Voice
  Voz TTS (default: es-MX-JorgeNeural)
.PARAMETER Agent
  Inicia el agente de fondo (voice-agent.pyw)
.PARAMETER Install
  Instala el agente en Windows startup
.PARAMETER Uninstall
  Desinstala el agente de Windows startup
.PARAMETER Status
  Muestra estado del agente
.EXAMPLE
  voice --record
  voice --speak "Hola mundo"
  voice --hear
  voice --listen --auto-type
  voice --agent
  voice --install
  voice --status
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

# --- Agent management ---
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
    Write-Error "voice-agent.pyw no encontrado en $ScriptDir"
    exit 1
  }
  Write-Host "Iniciando Voice Agent en segundo plano..." -ForegroundColor Cyan
  start-process pythonw -ArgumentList "`"$AgentScript`""
  return
}

# --- CLI commands ---
if (-not (Test-Path $CLI)) {
  Write-Error "voice-cli.py no encontrado en $ScriptDir"
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
