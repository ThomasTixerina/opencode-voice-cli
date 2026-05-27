# Voice CLI for OpenCode

Control por voz para [OpenCode AI](https://opencode.ai). Habla en lugar de escribir.

## Demo rapido

```bash
# Di esto en tu microfono:
"oye open... muestra los archivos del directorio actual plan"

# Aparece escrito automaticamente en tu terminal.
# El agente lee la respuesta en voz alta.
```

## Requisitos

- Python 3.10+
- ffmpeg (para reproduccion de audio en Windows)
- Groq API key (gratis: [console.groq.com](https://console.groq.com))

## Instalacion

```bash
# 1. Clonar
git clone https://github.com/ThomasTixerina/opencode-voice-cli.git
cd opencode-voice-cli

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Configurar API key
echo GROQ_API_KEY=gsk_tu_key_aqui > .env

# 4. Verificar ffmpeg
ffmpeg -version
```

## Uso

### CLI manual

```bash
python voice-cli.py --record
python voice-cli.py --speak "Hola mundo"
python voice-cli.py --hear
python voice-cli.py --listen --auto-type
python voice-cli.py --watch archivo.txt
```

### Agente de fondo (recomendado)

```powershell
# Instalar en Windows Startup (una vez)
.\install-agent.ps1 -Install
pythonw .\voice-agent.pyw

# Comandos rapidos
voice --agent
voice --status
voice --install
```

## Arquitectura

Dos componentes principales:

### voice-cli.py
CLI completa con modos manuales: record, speak, hear, listen, watch.

### voice-agent.pyw
Agente de fondo (pythonw.exe, sin ventana). Dos threads:

| Thread | Funcion |
|--------|--------|
| Audio capture | Captura audio, detecta "oye open...", transcribe con Groq Whisper, escribe en terminal activa con SendKeys |
| File watcher | Vigila `~/.opencode/voice-output.txt`, lee nuevos contenidos con edge-tts |

## Configuracion

Edita constantes en `voice-agent.pyw`:
```python
ENERGY_THRESHOLD = 0.02
SILENCE_SECONDS = 1.5
WAKE_WORDS = ["oye open", "oye abre", "escucha open"]
CLOSE_WORDS = ["plan", "build", "terminamos", "fin", "listo", "adelante"]
TTS_VOICE = "es-MX-JorgeNeural"
```

## Estructura

```
opencode-voice-cli/
  voice-cli.py          # CLI principal
  voice-agent.pyw       # Agente de fondo
  voice.ps1             # Wrapper PowerShell
  install-agent.ps1     # Instalador startup
  requirements.txt      # Dependencias
  .env.template         # Template API key
  .gitignore
  README.md
```

## Licencia

MIT
