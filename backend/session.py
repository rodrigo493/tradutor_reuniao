import asyncio
import datetime
from typing import Optional
from fastapi import WebSocket
from backend.audio import AudioCapture
from backend.transcriber import AudioWorker
from backend.tts import speak_to_device


class RecordingSession:
    """Sessão de intérprete bidirecional para um usuário.

    O idioma do usuário (``my_lang``) é escolhido na interface; o idioma do
    outro lado é detectado automaticamente a cada fala e "aprendido"
    (``other_lang`` começa com um palpite e é atualizado conforme a detecção).
    """

    def __init__(self, user_id: int, other_lang: str, websocket: WebSocket,
                 loop: Optional[asyncio.AbstractEventLoop],
                 my_lang: str = "pt",
                 headphone_index: Optional[int] = None,
                 vbcable_index: Optional[int] = None,
                 mic_index: Optional[int] = None,
                 loopback_index: Optional[int] = None,
                 anti_echo: bool = True,
                 tts_enabled: bool = True):
        self.user_id = user_id
        self.my_lang = my_lang
        # Palpite inicial do idioma do outro lado; atualizado por auto-detecção.
        self.other_lang = other_lang
        self.websocket = websocket
        self.loop = loop
        self.headphone_index = headphone_index
        self.vbcable_index = vbcable_index
        # Modo texto: quando False, não sintetiza/toca áudio (só mostra o texto
        # traduzido na tela), o que elimina a latência e os problemas do TTS.
        self.tts_enabled = tts_enabled
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
        if not self.tts_enabled:
            return  # modo texto: só mostra na tela, sem áudio
        if speaker == "Outro":
            # Tradução no MEU idioma, no fone do usuário. Pausa o loopback só se
            # houver risco de eco (saída no mesmo dispositivo que o loopback
            # captura).
            if self.headphone_index is None:
                return
            if self.anti_echo:
                self.audio.pause_loopback()
                try:
                    speak_to_device(translation, self.my_lang, self.headphone_index)
                finally:
                    self.audio.resume_loopback()
            else:
                speak_to_device(translation, self.my_lang, self.headphone_index)
        else:
            # tradução no idioma (auto-detectado) da outra pessoa, no VB-Cable
            if self.vbcable_index is not None:
                speak_to_device(translation, self.other_lang, self.vbcable_index)

    def _learn_other_lang(self, detected: str, confidence: float):
        """Atualiza o idioma do outro lado a partir da detecção do loopback."""
        if detected and detected != self.my_lang:
            self.other_lang = detected

    def start(self):
        self.audio.start()
        # Outro lado (loopback): detecta o idioma falado, traduz para o MEU
        # idioma e aprende qual é o idioma do outro. Descarta falas no meu
        # idioma (provável eco da minha própria tradução).
        worker_in = AudioWorker(
            self.audio.spk_queue, source_lang="auto", target_lang=self.my_lang,
            speaker="Outro", on_result=self._handle_result,
            detect=True, drop_langs=(self.my_lang,),
            on_detected=self._learn_other_lang,
        )
        # Minha fala (microfone): detecta o idioma e traduz para o idioma
        # (auto-detectado) do outro lado.
        worker_out = AudioWorker(
            self.audio.mic_queue, source_lang="auto",
            target_lang=(lambda: self.other_lang),
            speaker="Você", on_result=self._handle_result,
            detect=True, drop_langs=(),
        )
        worker_in.start()
        worker_out.start()
        self._workers = [worker_in, worker_out]

    def stop(self) -> list[dict]:
        self._active = False
        self.audio.stop()
        return self.transcriptions
