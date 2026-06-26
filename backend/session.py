import asyncio
import datetime
from typing import Optional
from fastapi import WebSocket
from backend.audio import AudioCapture
from backend.transcriber import AudioWorker
from backend.tts import speak_to_device

MY_LANG = "pt"


class RecordingSession:
    """Sessão de intérprete bidirecional para um usuário."""

    def __init__(self, user_id: int, other_lang: str, websocket: WebSocket,
                 loop: Optional[asyncio.AbstractEventLoop],
                 headphone_index: int, vbcable_index: int,
                 mic_index: Optional[int] = None,
                 loopback_index: Optional[int] = None,
                 anti_echo: bool = True):
        self.user_id = user_id
        self.other_lang = other_lang
        self.websocket = websocket
        self.loop = loop
        self.headphone_index = headphone_index
        self.vbcable_index = vbcable_index
        # Só pausar o loopback durante o TTS em PT se a saída em PT cai no
        # mesmo dispositivo capturado pelo loopback (senão não há eco e a pausa
        # só descartaria áudio da outra pessoa, picotando a captura).
        self.anti_echo = anti_echo
        self.audio = AudioCapture(mic_index=mic_index, loopback_index=loopback_index)
        self.transcriptions: list[dict] = []
        self.started_at = datetime.datetime.now()
        self._workers: list[AudioWorker] = []
        self._active = True

    def _send(self, entry: dict):
        if self.loop is not None:
            asyncio.run_coroutine_threadsafe(
                self.websocket.send_json(entry), self.loop
            )

    def _handle_result(self, speaker: str, original: str,
                       translation: str, detected_lang: str):
        if not self._active:
            return  # sessão encerrada: não enviar nem tocar backlog
        entry = {
            "type": "transcription",
            "speaker": speaker,
            "original": original,
            "translation": translation,
            "detected_lang": detected_lang,
            "timestamp": datetime.datetime.now().strftime("%H:%M:%S"),
        }
        self.transcriptions.append(entry)
        self._send(entry)
        if speaker == "Outro":
            # PT no fone do usuário. Pausa o loopback só se houver risco de eco
            # (PT saindo no mesmo dispositivo que o loopback captura).
            if self.anti_echo:
                self.audio.pause_loopback()
                try:
                    speak_to_device(translation, MY_LANG, self.headphone_index)
                finally:
                    self.audio.resume_loopback()
            else:
                speak_to_device(translation, MY_LANG, self.headphone_index)
        else:
            # tradução no idioma da outra pessoa, injetada no VB-Cable
            speak_to_device(translation, self.other_lang, self.vbcable_index)

    def start(self):
        self.audio.start()
        worker_in = AudioWorker(
            self.audio.spk_queue, source_lang="en", target_lang=MY_LANG,
            speaker="Outro", on_result=self._handle_result,
            detect=True, drop_langs=("pt",),
        )
        worker_out = AudioWorker(
            self.audio.mic_queue, source_lang=MY_LANG, target_lang=self.other_lang,
            speaker="Você", on_result=self._handle_result,
        )
        worker_in.start()
        worker_out.start()
        self._workers = [worker_in, worker_out]

    def stop(self) -> list[dict]:
        self._active = False
        self.audio.stop()
        return self.transcriptions
