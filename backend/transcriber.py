import concurrent.futures
import os
import time
import threading
from typing import Callable, Optional
from faster_whisper import WhisperModel
from deep_translator import GoogleTranslator
from backend.audio import save_audio_chunk, CHUNK_BYTES
from dotenv import load_dotenv

load_dotenv()

_model: Optional[WhisperModel] = None
_model_lock = threading.Lock()


def get_model() -> WhisperModel:
    global _model
    with _model_lock:
        if _model is None:
            model_size = os.getenv("WHISPER_MODEL", "base")
            for attempt in range(5):
                try:
                    _model = WhisperModel(model_size, device="cpu", compute_type="int8")
                    break
                except Exception as e:
                    if attempt < 4:
                        time.sleep(2 ** attempt)
                    else:
                        raise RuntimeError(f"Falha ao carregar Whisper após 5 tentativas: {e}")
    return _model


def translate_text(text: str, source: str, target: str) -> str:
    if source == target:
        return text
    try:
        return GoogleTranslator(source=source, target=target).translate(text)
    except Exception:
        return text


def transcribe_and_translate(
    audio_bytes: bytes,
    source_lang: str,
    target_lang: str,
    speaker: str,
    on_result: Callable[[str, str, str, str], None],
    detect: bool = False,
    drop_langs: tuple = (),
) -> None:
    print(f"[Transcriber] {len(audio_bytes)} bytes speaker={speaker} detect={detect}")
    path = save_audio_chunk(audio_bytes)
    try:
        model = get_model()
        lang_arg = None if detect else source_lang
        segments, info = model.transcribe(path, language=lang_arg)
        detected = getattr(info, "language", source_lang) or source_lang
        if detected in drop_langs:
            print(f"[Transcriber] descartado (idioma {detected} em drop_langs)")
            return
        original = " ".join(s.text for s in segments).strip()
        print(f"[Transcriber] [{detected}] '{original}'")
        if not original:
            return
        effective_source = detected if detect else source_lang
        translation = translate_text(original, effective_source, target_lang)
        on_result(speaker, original, translation, detected)
    except Exception as e:
        print(f"[Transcriber] ERRO: {e}")
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


class AudioWorker:
    """Consome fila de chunks de áudio e aciona transcrição em threads."""

    def __init__(self, queue, source_lang: str, target_lang: str,
                 speaker: str, on_result: Callable,
                 detect: bool = False, drop_langs: tuple = ()):
        self.queue = queue
        self.source_lang = source_lang
        self.target_lang = target_lang
        self.speaker = speaker
        self.on_result = on_result
        self.detect = detect
        self.drop_langs = drop_langs
        self._thread: Optional[threading.Thread] = None
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        self._inflight: Optional[concurrent.futures.Future] = None

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        buffer = b""
        while True:
            chunk = self.queue.get()
            if chunk is None:
                break
            buffer += chunk
            if len(buffer) >= CHUNK_BYTES:
                data = buffer
                buffer = b""
                # Tempo real: se ainda processa o chunk anterior, descarta o
                # atual em vez de empilhar (evita o delay crescer sem parar).
                if self._inflight is not None and not self._inflight.done():
                    continue
                self._inflight = self._executor.submit(
                    transcribe_and_translate, data, self.source_lang,
                    self.target_lang, self.speaker, self.on_result,
                    self.detect, self.drop_langs,
                )
        # Ao parar, cancela qualquer tarefa ainda na fila.
        self._executor.shutdown(wait=False, cancel_futures=True)
