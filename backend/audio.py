import asyncio
import queue
import threading
import wave
import tempfile
import os
import pyaudiowpatch as pyaudio

CHUNK = 1024
RATE = 16000
CHUNK_BYTES = RATE * 2 * 3  # 3 segundos de áudio

class AudioCapture:
    def __init__(self):
        self.mic_queue: queue.Queue = queue.Queue()
        self.spk_queue: queue.Queue = queue.Queue()
        self._running = False
        self._threads: list[threading.Thread] = []

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

    def _capture_mic(self):
        pa = pyaudio.PyAudio()
        stream = pa.open(format=pyaudio.paInt16, channels=1, rate=RATE,
                         input=True, frames_per_buffer=CHUNK)
        while self._running:
            self.mic_queue.put(stream.read(CHUNK, exception_on_overflow=False))
        stream.stop_stream()
        stream.close()
        pa.terminate()

    def _capture_loopback(self):
        pa = pyaudio.PyAudio()
        try:
            device = pa.get_default_wasapi_loopback()
            stream = pa.open(format=pyaudio.paInt16, channels=1, rate=RATE,
                             input=True, input_device_index=device["index"],
                             frames_per_buffer=CHUNK)
            while self._running:
                self.spk_queue.put(stream.read(CHUNK, exception_on_overflow=False))
            stream.stop_stream()
            stream.close()
        except Exception as e:
            print(f"Loopback não disponível: {e}")
        finally:
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
