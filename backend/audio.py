import asyncio
import queue
import threading
import time
import wave
import tempfile
import os
import pyaudiowpatch as pyaudio
from backend.audio_lock import PYAUDIO_LOCK

CHUNK = 1024
RATE = 16000
CHUNK_BYTES = RATE * 2 * 3  # 3 segundos de áudio

class AudioCapture:
    def __init__(self, mic_index: int | None = None, loopback_index: int | None = None):
        self.mic_queue: queue.Queue = queue.Queue()
        self.spk_queue: queue.Queue = queue.Queue()
        self._running = False
        self._threads: list[threading.Thread] = []
        self.mic_index = mic_index
        self.loopback_index = loopback_index
        self.loopback_paused = False
        self._discard_until = 0.0

    def start(self):
        self._running = True
        self._threads = [
            threading.Thread(target=self._capture_mic, daemon=True),
            threading.Thread(target=self._capture_loopback, daemon=True),
        ]
        for t in self._threads:
            t.start()

    def stop(self):
        self._running = False
        self.mic_queue.put(None)
        self.spk_queue.put(None)

    def pause_loopback(self):
        self.loopback_paused = True
        # Drain already-buffered audio so stale frames don't leak through
        while True:
            try:
                self.spk_queue.get_nowait()
            except queue.Empty:
                break

    def resume_loopback(self):
        self.loopback_paused = False
        # Discard stream tail for 400 ms after resuming to flush device buffer
        self._discard_until = time.monotonic() + 0.4

    def _capture_mic(self):
        pa = None
        try:
            with PYAUDIO_LOCK:
                pa = pyaudio.PyAudio()
                stream = pa.open(format=pyaudio.paInt16, channels=1, rate=RATE,
                                 input=True, frames_per_buffer=CHUNK,
                                 input_device_index=self.mic_index)
            print("[Audio] Microfone iniciado")
            count = 0
            while self._running:
                data = stream.read(CHUNK, exception_on_overflow=False)
                self.mic_queue.put(data)
                count += 1
                if count % 50 == 0:
                    print(f"[Audio] Mic: {count} chunks capturados")
            stream.stop_stream()
            stream.close()
        except Exception as e:
            print(f"[Audio] Mic ERRO: {e}")
        finally:
            if pa is not None:
                pa.terminate()

    def _capture_loopback(self):
        import numpy as np
        pa = None
        try:
            with PYAUDIO_LOCK:
                pa = pyaudio.PyAudio()
                if self.loopback_index is not None:
                    device = pa.get_device_info_by_index(self.loopback_index)
                else:
                    device = pa.get_default_wasapi_loopback()
                native_rate = int(device["defaultSampleRate"])  # geralmente 48000
                native_channels = max(1, int(device["maxInputChannels"]))
                # Ajusta chunk para o rate nativo
                native_chunk = int(CHUNK * native_rate / RATE)
                stream = pa.open(format=pyaudio.paInt16, channels=native_channels,
                                 rate=native_rate, input=True,
                                 input_device_index=device["index"],
                                 frames_per_buffer=native_chunk)
            ratio = RATE / native_rate
            while self._running:
                raw = stream.read(native_chunk, exception_on_overflow=False)
                arr = np.frombuffer(raw, dtype=np.int16)
                # Mixar para mono se necessário
                if native_channels == 2:
                    arr = arr.reshape(-1, 2).mean(axis=1).astype(np.int16)
                # Resample para 16000 Hz via interpolação linear
                if native_rate != RATE:
                    n_out = max(1, int(len(arr) * ratio))
                    indices = np.linspace(0, len(arr) - 1, n_out)
                    arr = np.interp(indices, np.arange(len(arr)), arr).astype(np.int16)
                if self.loopback_paused or time.monotonic() < self._discard_until:
                    continue
                self.spk_queue.put(arr.tobytes())
            stream.stop_stream()
            stream.close()
        except Exception as e:
            print(f"Loopback não disponível: {e}")
        finally:
            if pa is not None:
                pa.terminate()


def save_audio_chunk(audio_bytes: bytes) -> str:
    """Salva chunk em arquivo WAV temporário. Retorna caminho."""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        path = f.name
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(RATE)
        wf.writeframes(audio_bytes)
    return path
