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


STATE_IDLE = 0
STATE_LISTENING = 1
STATE_PROCESSING = 2
STATE_SPEAKING = 3

_agent_state = STATE_IDLE
_state_lock = threading.Lock()

def set_state(s):
    global _agent_state
    with _state_lock:
        _agent_state = s

def get_state():
    with _state_lock:
        return _agent_state


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


def normalize(text):
    text = text.lower().strip()
    for ch in ".,!?¿¡:;\"'()-":
        text = text.replace(ch, " ")
    return " ".join(text.split())


def extract_command(text):
    raw = text
    text_lower = text.lower()
    wake_found = None
    ww_pos = -1
    for ww in WAKE_WORDS:
        idx = text_lower.find(ww)
        if idx >= 0:
            wake_found = ww
            ww_pos = idx
            break
    if wake_found is None:
        return None

    cmd = raw[ww_pos + len(wake_found):].strip().strip(".,!?¿¡:;\"'() ")

    for cw in CLOSE_WORDS:
        idx = cmd.lower().find(cw)
        if idx >= 0:
            cmd = cmd[:idx].strip()
            break

    if not cmd:
        log("Wake word detectado pero comando vacio")
        return None
    return cmd


def type_keys(text):
    if not text:
        return
    escaped = text.replace("'", "''").replace("{", "{{}").replace("}", "{}}")
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


def clean_tts(text):
    text = text.strip()
    text = text.lstrip("\ufeff\u00a0")
    text = text.replace("\ufeff", "").replace("\u00a0", " ")
    text = "".join(c for c in text if c.isprintable() or c in " \n.,!?¿¡:;\"'()-")
    return text.strip()


def speak_text(text):
    text = clean_tts(text)
    if not text:
        return

    def _play():
        set_state(STATE_SPEAKING)
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
            set_state(STATE_IDLE)

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
                        set_state(STATE_LISTENING)
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
                            set_state(STATE_PROCESSING)

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
                                    set_state(STATE_IDLE)
                            else:
                                log("Transcripcion vacia")
                                set_state(STATE_IDLE)
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
                with open(OUTPUT_FILE, "r", encoding="utf-8-sig") as f:
                    f.seek(_last_output_pos)
                    new_content = f.read().strip()
                _last_output_pos = OUTPUT_FILE.stat().st_size
                if new_content:
                    log(f"Respuesta: {new_content[:80]}...")
                    speak_text(new_content)
            elif size == 0 or size < _last_output_pos:
                _last_output_pos = 0
        except Exception as e:
            log(f"Watcher error: {e}")
        time.sleep(1)


def indicator_loop():
    try:
        import tkinter as tk

        S = {"bg": "#1a1a1a", "fg": "white", "font": ("Segoe UI", 10, "bold")}
        COLORS = {STATE_IDLE: "#22c55e", STATE_LISTENING: "#eab308", STATE_PROCESSING: "#3b82f6", STATE_SPEAKING: "#ef4444"}
        TEXTS  = {STATE_IDLE: "Escuchando", STATE_LISTENING: "Escuchando...", STATE_PROCESSING: "Procesando...", STATE_SPEAKING: "Hablando..."}
        LABELS = {STATE_IDLE: "Activo", STATE_LISTENING: "Te escucho", STATE_PROCESSING: "Pensando", STATE_SPEAKING: "Hablando"}

        root = tk.Tk()
        root.title("Voice Agent")
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.attributes("-alpha", 0.88)
        root.configure(bg="#1a1a1a")

        sw = root.winfo_screenwidth()
        root.geometry(f"200x42+{sw-210}+10")

        frame = tk.Frame(root, bg="#1a1a1a", highlightbackground="#333", highlightthickness=1)
        frame.pack(fill="both", expand=True)

        dot = tk.Label(frame, text="\u25cf", fg=COLORS[STATE_IDLE], bg="#1a1a1a",
                       font=("Segoe UI", 16))
        dot.pack(side="left", padx=(10, 5), pady=8)

        status = tk.Label(frame, text=TEXTS[STATE_IDLE], fg="white", bg="#1a1a1a",
                          font=("Segoe UI", 10))
        status.pack(side="left", padx=5)

        label = tk.Label(frame, text=LABELS[STATE_IDLE], fg="#999", bg="#1a1a1a",
                         font=("Segoe UI", 9))
        label.pack(side="right", padx=10)

        def update():
            s = get_state()
            dot.config(fg=COLORS.get(s, COLORS[STATE_IDLE]))
            status.config(text=TEXTS.get(s, TEXTS[STATE_IDLE]))
            label.config(text=LABELS.get(s, LABELS[STATE_IDLE]))
            root.after(250, update)

        root.after(250, update)
        root.mainloop()
    except Exception as e:
        log(f"Indicator no disponible: {e}")


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

    t_audio = threading.Thread(target=audio_capture_loop, daemon=True)
    t_watch = threading.Thread(target=file_watcher_loop, daemon=True)
    t_audio.start()
    t_watch.start()

    log("Voice Agent listo")

    indicator_loop()

    log("Voice Agent detenido")


if __name__ == "__main__":
    main()
