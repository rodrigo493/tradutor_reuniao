import asyncio
import datetime
from typing import Optional
from fastapi import WebSocket
from backend.audio import AudioCapture
from backend.transcriber import AudioWorker
from backend.tts import speak_text

class RecordingSession:
    """Gerencia uma sessão de gravação ativa para um usuário."""

    def __init__(self, user_id: int, my_lang: str, other_lang: str,
                 websocket: WebSocket, loop: asyncio.AbstractEventLoop):
        self.user_id = user_id
        self.my_lang = my_lang
        self.other_lang = other_lang
        self.websocket = websocket
        self.loop = loop
        self.audio = AudioCapture()
        self.transcriptions: list[dict] = []
        self.started_at = datetime.datetime.now()
        self._workers: list[AudioWorker] = []

    def start(self):
        self.audio.start()

        def on_result(speaker: str, original: str, translation: str):
            hora = datetime.datetime.now().strftime("%H:%M:%S")
            entry = {
                "type": "transcription",
                "speaker": speaker,
                "original": original,
                "translation": translation,
                "timestamp": hora,
            }
            self.transcriptions.append(entry)
            # Envia do thread de background para o loop asyncio principal
            asyncio.run_coroutine_threadsafe(
                self.websocket.send_json(entry),
                self.loop
            )
            # TTS só para o que o OUTRO fala (loopback → fone do usuário)
            if speaker == "Outro":
                speak_text(translation, self.my_lang)

        worker_mic = AudioWorker(
            self.audio.mic_queue, self.my_lang, self.other_lang, "Você", on_result
        )
        worker_spk = AudioWorker(
            self.audio.spk_queue, self.other_lang, self.my_lang, "Outro", on_result
        )
        worker_mic.start()
        worker_spk.start()
        self._workers = [worker_mic, worker_spk]

    def stop(self) -> list[dict]:
        self.audio.stop()
        return self.transcriptions
