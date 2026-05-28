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
# O edita .env directamente

# 4. Verificar ffmpeg
ffmpeg -version
# Si no lo tienes: winget install ffmpeg
```

## Uso

### CLI manual

```bash
# Grabar y transcribir (copia al portapapeles)
python voice-cli.py --record

# Leer texto en voz alta
python voice-cli.py --speak "Hola mundo"

# Leer el portapapeles en voz alta
python voice-cli.py --hear

# Modo wake word + auto-type (escribe en terminal activa)
python voice-cli.py --listen --auto-type

# Vigilar archivo y leer cambios en voz alta
python voice-cli.py --watch archivo.txt

# Parametros opcionales
python voice-cli.py --duration 10        # Duracion max (default: 5s)
python voice-cli.py --voice es-MX-JorgeNeural  # Voz TTS
```

### PowerShell wrapper

```powershell
.\voice.ps1 --record
.\voice.ps1 --speak "Hola"
.\voice.ps1 --hear
.\voice.ps1 --listen --auto-type
.\voice.ps1 --status
.\voice.ps1 --install
```

### Agente de fondo (recomendado)

```powershell
# Instalar en Windows Startup (una vez)
.\install-agent.ps1 -Install
pythonw .\voice-agent.pyw

# Comandos rapidos
voice --agent       # Iniciar agente
voice --status      # Ver estado
voice --install     # Agregar a startup
voice --uninstall   # Quitar de startup
```

## Arquitectura

### voice-cli.py
CLI completa con modos: `--record`, `--speak`, `--hear`, `--listen`, `--watch`.

### voice-agent.pyw
Agente de fondo que se ejecuta con `pythonw.exe` (sin ventana de consola). Tres componentes:

| Componente | Funcion |
|------------|---------|
| Audio capture | Captura audio del microfono, detecta "oye open..." via Groq Whisper, extrae el comando, lo escribe en la terminal activa con SendKeys |
| File watcher | Vigila `~/.opencode/voice-output.txt`, lee nuevos contenidos en voz alta con edge-tts |
| Indicador visual | Ventana tkinter en la esquina superior derecha con el estado actual |

### Indicador visual

Una ventana semitransparente aparece en la esquina superior derecha:

| Color | Estado | Significado |
|-------|--------|-------------|
| ● Verde | Activo | Esperando "oye open..." |
| ● Amarillo | Te escucho | Detecto voz, grabando |
| ● Azul | Pensando | Transcribiendo con Whisper |
| ● Rojo | Hablando | Reproduciendo respuesta TTS |

### Como funciona la entrada por voz

1. El agente captura audio en chunks de 0.5s
2. Cuando detecta voz (energia > umbral), el indicador cambia a amarillo
3. Cuando hay silencio por 1.5s, envia el audio a Groq Whisper, indicador cambia a azul
4. Si la transcripcion contiene "oye open..." (con o sin puntuacion), extrae el comando
5. El texto se escribe en la terminal activa via PowerShell SendKeys
6. El agente confirma con un TTS breve

### Como funciona la salida TTS

1. OpenCode escribe la respuesta en `~/.opencode/voice-output.txt`
2. El file watcher detecta el cambio
3. edge-tts genera audio MP3, indicador cambia a rojo
4. ffmpeg convierte a WAV
5. winsound reproduce el audio, indicador vuelve a verde

## Voces TTS disponibles

```bash
# Ver todas las voces en espanol
edge-tts --list-voices | findstr es-

# Recomendadas:
es-MX-JorgeNeural  # Masculino mexicano (default)
es-MX-DaliaNeural  # Femenino mexicano
es-ES-AlvaroNeural # Masculino espanol
es-ES-ElviraNeural # Femenino espanol
```

## Configuracion

Edita las constantes al inicio de `voice-agent.pyw`:

```python
ENERGY_THRESHOLD = 0.02   # Sensibilidad del microfono
SILENCE_SECONDS = 1.5     # Silencio para finalizar frase
MAX_RECORD_SECONDS = 15   # Duracion maxima de grabacion
WAKE_WORDS = ["oye open", "oye abre", "escucha open"]
CLOSE_WORDS = ["plan", "build", "terminamos", "fin", "listo", "adelante"]
TTS_VOICE = "es-MX-JorgeNeural"
```

## Estructura del proyecto

```
opencode-voice-cli/
  voice-cli.py          # CLI principal
  voice-agent.pyw       # Agente de fondo (pythonw)
  voice.ps1             # Wrapper PowerShell
  install-agent.ps1     # Instalador startup
  requirements.txt      # Dependencias Python
  .env                  # API keys (no se sube)
  .env.template         # Template para .env
  README.md             # Este archivo
```

## Licencia

MIT
