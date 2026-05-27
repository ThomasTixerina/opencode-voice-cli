#!/usr/bin/env python3
"""voice-cli.py — Habla con OpenCode AI usando Groq Whisper + edge-tts

Uso:
  python voice-cli.py --record              Graba voz -> portapapeles
  python voice-cli.py --speak "texto"       Lee texto en voz alta
  python voice-cli.py --listen --auto-type  [Fase2] Wake word + escribe en terminal activa
  python voice-cli.py --hear                Lee el portapapeles en voz alta
  python voice-cli.py --watch ARCHIVO       Vigila archivo y lee cambios en voz alta
"""

import os
import sys
import tempfile
import time
import re
import argparse
import subprocess
import asyncio
import json
import shutil
from pathlib import Path

import numpy as np

try:
    import sounddevice as sd
    import soundfile as sf
except ImportError:
    sd = None
    sf = None

import pyperclip

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from groq import Groq
import edge_tts


# —─ Config —────────────────────────────────────────────────────────────────
GROQ_MODEL = "whisper-large-v3"
LANG = "es"
RATE = 16000
CHANNELS = 1
MAX_RECORD_SEC = 30
SILENCE_SECS = 2.0
ENERGY_THRESHOLD = 0.02

WAKE_WORDS = ["oye open", "oye abre", "escucha open"]
CLOSE_WORDS = ["plan", "build", "terminamos", "termina", "fin", "listo", "adelante"]
TTS_VOICE = "es-MX-JorgeNeural"

OPENCODE_OUTPUT_FILE = Path.home() / ".opencode" / "voice-output.txt"

G = "\033[92m"
Y = "\033[93m"
C = "\033[96m"
R = "\033[91m"
B = "\033[1m"
N = "\033[0m"


# —─ Groq —────────────────────────────────────────────────────────────
_client = None

def get_client():
    global _client
    if _client is None:
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            print(f"{R}Error: GROQ_API_KEY no esta configurada.{N}")
            print(f"{Y}Crea un archivo .env en {Path(__file__).parent} con:{N}")
            print(f"  GROQ_API_KEY=gsk_tu_key_aqui")
            sys.exit(1)
        _client = Groq(api_key=api_key)
    return _client


# —─ Record —───────────────────────────────────────────────────────
record_audio_func = None

def record_audio(duration=None):
    if sd is None:
        print(f"{R}Error: sounddevice no instalado.{N}")
        sys.exit(1)

    print(f"{G}[MIC] Grabando...{N}", end="", flush=True)

    if duration:
        audio = sd.rec(int(duration * RATE), samplerate=RATE, channels=CHANNELS, dtype="float32")
        sd.wait()
        print()
        return audio

    buffer = []
    silent_chunks = 0
    chunk_sec = 0.5
    chunk_samples = int(RATE * chunk_sec)
    started = False
    max_chunks = int(MAX_RECORD_SEC / chunk_sec)

    stream = sd.InputStream(samplerate=RATE, channels=CHANNELS, dtype="float32")
    stream.start()

    try:
        for _ in range(max_chunks):
            chunk, _ = stream.read(chunk_samples)
            rms = np.sqrt(np.mean(chunk ** 2))

            if rms > ENERGY_THRESHOLD:
                if not started:
                    started = True
                    print(f"\r{G}[MIC] Grabando... (silencio para parar){N}", end="", flush=True)
                silent_chunks = 0
            elif started:
                silent_chunks += 1
                if silent_chunks >= int(SILENCE_SECS / chunk_sec):
                    break

            if started:
                buffer.append(chunk)
                bar = "#" * min(int(rms * 200), 20)
                print(f"\r{G}[MIC] {bar:<20}{N}", end="", flush=True)

    except KeyboardInterrupt:
        print(f"\n{Y}[STOP] Cancelado{N}")
    finally:
        stream.stop()
        stream.close()

    print()
    if not buffer:
        print(f"{Y}No se detecto voz.{N}")
        return None
    return np.concatenate(buffer)


def transcribe(audio):
    if audio is None:
        return None
    client = get_client()
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        tmp_path = f.name
    sf.write(tmp_path, audio, RATE)
    try:
        with open(tmp_path, "rb") as f:
            resp = client.audio.transcriptions.create(
                file=(Path(tmp_path).name, f),
                model=GROQ_MODEL,
                language=LANG,
                response_format="json",
            )
        return resp.text.strip()
    finally:
        os.unlink(tmp_path)


def clip(text):
    try:
        pyperclip.copy(text)
        return True
    except Exception:
        return False


# —─ TTS —──────────────────────────────────────────────────────────
async def _speak_async(text, voice=None):
    voice = voice or TTS_VOICE
    tmp = Path(tempfile.mktemp(suffix=".mp3"))
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(str(tmp))

    if os.name == "nt":
        wav = tmp.with_suffix(".wav")
        subprocess.run(["ffmpeg", "-y", "-i", str(tmp), str(wav)],
                       capture_output=True, check=True)
        import winsound
        winsound.PlaySound(str(wav), winsound.SND_FILENAME)
        wav.unlink(missing_ok=True)
    else:
        subprocess.run(["ffplay", "-nodisp", "-autoexit", str(tmp)],
                       capture_output=True, check=False)
    tmp.unlink(missing_ok=True)


def speak(text, voice=None):
    if not text:
        return
    print(f"{C}[SPEAK] Reproduciendo...{N}")
    asyncio.run(_speak_async(text, voice))


# —─ Introduce texto en la ventana activa (SendKeys) —───────────────────────────
send_keys_func = None

def type_keys(text):
    if not text:
        return
    escaped = text.replace("'", "''").replace("{", "{{").replace("}", "}}")
    ps = (
        f'Add-Type -AssemblyName System.Windows.Forms; '
        f"[System.Windows.Forms.SendKeys]::SendWait('{escaped}')"
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=False)


# —─ Hear: lee el portapapeles —───────────────────────────────────────
def hear_mode(voice=None):
    try:
        text = pyperclip.paste()
    except Exception:
        text = ""

    if not text or not text.strip():
        print(f"{Y}El portapapeles esta vacio.{N}")
        return

    print(f"{C}[HEAR] Leyendo portapapeles ({len(text.strip())} caracteres)...{N}")
    speak(text.strip(), voice)


# —─ Watch: vigila un archivo y lee cambios —──────────────────────────────
def watch_mode(filepath, voice=None):
    path = Path(filepath)
    if not path.exists():
        path.write_text("", encoding="utf-8")

    print(f"{C}[WATCH] Vigilando: {path}{N}")
    print(f"{Y}Ctrl+C para salir{N}")
    last_size = path.stat().st_size

    try:
        while True:
            time.sleep(1)
            current_size = path.stat().st_size
            if current_size > last_size:
                with open(path, "r", encoding="utf-8") as f:
                    f.seek(last_size)
                    new_content = f.read().strip()
                last_size = current_size
                if new_content:
                    print(f"{G}[WATCH] Nuevo contenido detectado{N}")
                    speak(new_content, voice)
            elif current_size < last_size:
                last_size = current_size
    except KeyboardInterrupt:
        print(f"\n{Y}[STOP] Watch detenido.{N}")


# —─ Listen: wake word + auto-type —────────────────────────────────
def listen_mode(auto_type=False, voice=None):
    if sd is None:
        print(f"{R}Error: sounddevice no instalado.{N}")
        sys.exit(1)

    print(f"{B}{C}+----------------------------------------+{N}")
    print(f"{B}{C}|   [LISTEN] Escuchando 'oye open...'   |{N}")
    if auto_type:
        print(f"{B}{C}|   Auto-type: ACTIVADO (escribe en     |{N}")
        print(f"{B}{C}|   la terminal activa)                |{N}")
    print(f"{B}{C}+----------------------------------------+{N}")
    print(f"{Y}Ctrl+C para salir{N}")

    chunk_sec = 0.5
    chunk_samples = int(RATE * chunk_sec)
    stream = sd.InputStream(samplerate=RATE, channels=CHANNELS, dtype="float32")
    stream.start()

    speech_buffer = []
    is_speaking = False
    silent_chunks = 0

    try:
        while True:
            chunk, _ = stream.read(chunk_samples)
            rms = np.sqrt(np.mean(chunk ** 2))

            if rms > ENERGY_THRESHOLD:
                if not is_speaking:
                    is_speaking = True
                    speech_buffer = [chunk]
                else:
                    speech_buffer.append(chunk)
                silent_chunks = 0
            else:
                if is_speaking:
                    silent_chunks += 1
                    speech_buffer.append(chunk)
                    if silent_chunks >= int(SILENCE_SECS / chunk_sec):
                        audio = np.concatenate(speech_buffer)
                        is_speaking = False
                        speech_buffer = []

                        print(f"\r{C}[WAIT] Transcribiendo...{N}")
                        text = transcribe(audio)

                        if text:
                            process_command(text, auto_type, voice)
                        else:
                            print(f"\r{Y}No se entendio.{N}")
                        print(f"\r{C}[LISTEN] Escuchando...{N}", end="", flush=True)

    except KeyboardInterrupt:
        print(f"\n{Y}[STOP] Listen detenido.{N}")
    finally:
        stream.stop()
        stream.close()


def process_command(text, auto_type=False, voice=None):
    text_lower = text.lower().strip()

    wake_found = None
    for w in WAKE_WORDS:
        if w in text_lower:
            wake_found = w
            break

    if not wake_found:
        return

    idx = text_lower.index(wake_found)
    cmd = text[idx + len(wake_found):].strip()

    close_found = None
    for c in CLOSE_WORDS:
        if c in cmd.lower():
            close_found = c
            break

    if close_found:
        idx = cmd.lower().rindex(close_found)
        cmd = cmd[:idx].strip()

    if not cmd:
        print(f"\r{Y}[!] No se detecto comando despues de '{wake_found}'.{N}")
        return

    print(f"\n{B}{G}[TEXT] Transcripcion:{N} {text}")
    print(f"{B}{C}[>>] Comando:{N} {cmd}")

    clip(cmd)

    if auto_type:
        print(f"{B}[TYPE] Escribiendo en terminal activa...{N}")
        time.sleep(0.5)
        type_keys(cmd)

    asyncio.run(_speak_async(f"Comando listo: {cmd[:80]}", voice))


# —─ Main —──────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Voice CLI — Habla con OpenCode AI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Ejemplos:\n"
            '  python voice-cli.py --record              Grabar y transcribir\n'
            '  python voice-cli.py --speak "texto"       Leer texto en voz alta\n'
            '  python voice-cli.py --hear                Leer portapapeles en voz alta\n'
            '  python voice-cli.py --listen --auto-type  [Fase2] Wake word + auto-type\n'
            '  python voice-cli.py --watch archivo.txt   [Fase2] Vigilar y leer cambios\n'
        )
    )

    group = parser.add_mutually_exclusive_group()
    group.add_argument("--record", action="store_true", help="Grabar y transcribir")
    group.add_argument("--speak", type=str, metavar="TEXTO", help="Leer texto")
    group.add_argument("--hear", action="store_true", help="Leer portapapeles")
    group.add_argument("--listen", action="store_true", help="[Fase2] Modo wake word")
    group.add_argument("--watch", type=str, metavar="ARCHIVO", help="[Fase2] Vigilar archivo")

    parser.add_argument("--auto-type", action="store_true", help="Auto-escribir en terminal activa")
    parser.add_argument("--duration", type=float, default=5, help="Duracion grabacion (segundos)")
    parser.add_argument("--voice", type=str, default=TTS_VOICE, help=f"Voz TTS (default: {TTS_VOICE})")

    args = parser.parse_args()

    if not any([args.record, args.speak, args.hear, args.listen, args.watch]):
        parser.print_help()
        return

    if args.record:
        audio = record_audio(duration=args.duration)
        if audio is None:
            return
        print(f"{C}[WAIT] Transcribiendo...{N}")
        text = transcribe(audio)
        if text:
            print(f"\n{B}{G}TEXT:{N} {text}")
            clip(text)
            print(f"{Y}[CLIP] Copiado al portapapeles.{N}")
        else:
            print(f"{R}No se pudo transcribir.{N}")

    elif args.speak:
        speak(args.speak, args.voice)

    elif args.hear:
        hear_mode(args.voice)

    elif args.watch:
        watch_mode(args.watch, args.voice)

    elif args.listen:
        listen_mode(auto_type=args.auto_type, voice=args.voice)


if __name__ == "__main__":
    main()
