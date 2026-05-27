# voice-agent.pyw runs with pythonw.exe (no console window)
import asyncio
import json
import os
import subprocess
import sys
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path

import numpy as np
import sounddevice as sd
import soundfile as sf
from groq import Groq

ENERGY_THRESHOLD = 0.02
RATE = 16000
CHANNELS = 1
CHUNK_SECONDS = 0.5
SILENCE_SECONDS = 1.5
MAX_RECORD_SECONDS = 15

WAKE_WORDS = ["oye open", "oye abre", "escucha open"]
CLOSE_WORDS = ["plan", "build", "terminamos", "termina", "fin", "listo", "adelante"]
TTS_VOICE = "es-MX-JorgeNeural"

HOME = Path.home()
OPENCODE_DIR = HOME / ".opencode"
OUTPUT_FILE = OPENCODE_DIR / "voice-output.txt"
LOG_FILE = OPENCODE_DIR / "voice-agent.log"
TMP_MP3 = OPENCODE_DIR / "_tts.mp3"
TMP_WAV = OPENCODE_DIR / "_tts.wav"

_client = None
_last_output_pos = 0


def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {msg}\n")
    except Exception:
        pass


def get_groq_client():
    global _client
    if _client is not None:
        return _client
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        env_path = HOME / "voice-cli" / ".env"
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                if line.startswith("GROQ_API_KEY="):
                    parts = line.split("=", 1)
                    if len(parts) > 1:
                        api_key = parts[1].strip().strip("\"'")
                    break
    if not api_key:
        log("ERROR: GROQ_API_KEY no encontrada")
        return None
    _client = Groq(api_key=api_key)
    return _client


def transcribe(audio_data):
    client = get_groq_client()
    if client is None:
        return ""
    import tempfile
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp_path = tmp.name
    tmp.close()
    try:
        sf.write(tmp_path, audio_data, RATE)
        with open(tmp_path, "rb") as f:
            result = client.audio.transcriptions.create(
                file=(os.path.basename(tmp_path), f),
                model="whisper-large-v3",
                language="es",
                response_format="json",
            )
        return result.text.strip()
    except Exception as e:
        log(f"Whisper error: {e}")
        return ""
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


def extract_command(text):
    text_lower = text.lower()
    wake_found = None
    pos = -1
    for ww in WAKE_WORDS:
        idx = text_lower.find(ww)
        if idx >= 0:
            wake_found = ww
            pos = idx + len(ww)
            break
    if wake_found is None:
        return None

    cmd = text[pos:].strip().strip(".,!?¿¡:; ")

    for cw in CLOSE_WORDS:
        idx = cmd.lower().find(cw)
        if idx >= 0:
            cmd = cmd[:idx].strip()
            break

    return cmd if cmd else None


def type_keys(text):
    if not text:
        return
    escaped = text.replace("'", "''").replace("{", "{{").replace("}", "}}")
    escaped = escaped.replace("~", "{~}").replace("^", "{^}").replace("%", "{%}").replace("+", "{+}")
    ps = (
        "Add-Type -AssemblyName System.Windows.Forms; "
        f"[System.Windows.Forms.SendKeys]::SendWait('{escaped}')"
    )
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
            timeout=10,
        )
    except Exception as e:
        log(f"SendKeys error: {e}")


def speak_text(text):
    def _play():
        try:
            async def _gen():
                import edge_tts
                communicate = edge_tts.Communicate(text, TTS_VOICE)
                await communicate.save(str(TMP_MP3))
            asyncio.run(_gen())
            subprocess.run(
                ["ffmpeg", "-y", "-i", str(TMP_MP3), "-ar", "44100", "-ac", "1", str(TMP_WAV)],
                capture_output=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            import winsound
            winsound.PlaySound(str(TMP_WAV), winsound.SND_FILENAME)
        except Exception as e:
            log(f"TTS error: {e}")
        finally:
            try:
                TMP_MP3.unlink(missing_ok=True)
                TMP_WAV.unlink(missing_ok=True)
            except Exception:
                pass

    t = threading.Thread(target=_play, daemon=True)
    t.start()


def audio_capture_loop():
    log("Audio capture iniciado")
    chunk_samples = int(RATE * CHUNK_SECONDS)

    try:
        with sd.InputStream(samplerate=RATE, channels=CHANNELS, dtype="float32") as stream:
            speech_buffer = []
            is_speaking = False
            silent_chunks = 0
            silence_threshold = int(SILENCE_SECONDS / CHUNK_SECONDS)

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
                        if silent_chunks >= silence_threshold or len(speech_buffer) * CHUNK_SECONDS > MAX_RECORD_SECONDS:
                            audio = np.concatenate(speech_buffer)
                            is_speaking = False
                            speech_buffer = []

                            log(f"Audio capturado ({len(audio)/RATE:.1f}s)")
                            text = transcribe(audio)
                            if text:
                                log(f"Transcripcion: {text[:120]}")
                                cmd = extract_command(text)
                                if cmd:
                                    log(f"Comando extraido: {cmd}")
                                    type_keys(cmd)
                                    speak_text(f"Listo: {cmd[:60]}")
                                else:
                                    log("No contiene wake word")
                            else:
                                log("Transcripcion vacia")
    except Exception as e:
        log(f"Audio error: {e}")
        log(traceback.format_exc())


def file_watcher_loop():
    global _last_output_pos
    log("File watcher iniciado")

    OPENCODE_DIR.mkdir(parents=True, exist_ok=True)
    if not OUTPUT_FILE.exists():
        OUTPUT_FILE.write_text("", encoding="utf-8")

    _last_output_pos = OUTPUT_FILE.stat().st_size

    while True:
        try:
            size = OUTPUT_FILE.stat().st_size
            if size > _last_output_pos:
                with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
                    f.seek(_last_output_pos)
                    new_content = f.read().strip()
                _last_output_pos = size
                if new_content:
                    log(f"Leyendo respuesta: {new_content[:80]}...")
                    speak_text(new_content)
            elif size < _last_output_pos:
                _last_output_pos = 0
        except Exception as e:
            log(f"Watcher error: {e}")
        time.sleep(1)


def main():
    OPENCODE_DIR.mkdir(parents=True, exist_ok=True)
    log("=" * 40)
    log("Voice Agent iniciado (pythonw)")
    log(f"Wake words: {WAKE_WORDS}")
    log(f"Close words: {CLOSE_WORDS}")
    log(f"Output: {OUTPUT_FILE}")
    log(f"Log: {LOG_FILE}")

    if not get_groq_client():
        log("ERROR FATAL: No hay GROQ_API_KEY")
        return

    t1 = threading.Thread(target=audio_capture_loop, daemon=True)
    t2 = threading.Thread(target=file_watcher_loop, daemon=True)
    t1.start()
    t2.start()

    log("Voice Agent listo")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        log("Voice Agent detenido")


if __name__ == "__main__":
    main()
