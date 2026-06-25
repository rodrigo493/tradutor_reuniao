import asyncio
import tempfile
import os
import threading
import edge_tts
import pyaudiowpatch as pyaudio
from backend.audio_output import mp3_to_pcm, play_pcm_to_device
from backend.audio_lock import PYAUDIO_LOCK

VOICE_MAP = {
    "pt": "pt-BR-FranciscaNeural",
    "en": "en-US-JennyNeural",
    "es": "es-ES-ElviraNeural",
    "fr": "fr-FR-DeniseNeural",
    "de": "de-DE-KatjaNeural",
    "it": "it-IT-ElsaNeural",
    "ja": "ja-JP-NanamiNeural",
    "zh": "zh-CN-XiaoxiaoNeural",
    "ar": "ar-SA-ZariyahNeural",
    "ru": "ru-RU-SvetlanaNeural",
    "ko": "ko-KR-SunHiNeural",
}

def get_voice(lang: str) -> str:
    return VOICE_MAP.get(lang, "pt-BR-FranciscaNeural")

async def synthesize_to_file(text: str, lang: str) -> str:
    """Converte texto para MP3 via edge-tts. Retorna caminho do arquivo."""
    voice = get_voice(lang)
    communicate = edge_tts.Communicate(text, voice)
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        mp3_path = f.name
    await communicate.save(mp3_path)
    return mp3_path

def play_audio_file(path: str):
    """Toca arquivo de áudio MP3 via sistema operacional."""
    import subprocess
    import sys
    if sys.platform == "win32":
        os.startfile(path)
    else:
        subprocess.Popen(["xdg-open", path])

def speak_text(text: str, lang: str):
    """Sintetiza e toca texto em thread separada (não bloqueia)."""
    def _run():
        loop = asyncio.new_event_loop()
        try:
            mp3_path = loop.run_until_complete(synthesize_to_file(text, lang))
            play_audio_file(mp3_path)
        except Exception as e:
            print(f"TTS erro: {e}")
        finally:
            loop.close()
    threading.Thread(target=_run, daemon=True).start()


async def synthesize_to_mp3_bytes(text: str, lang: str) -> bytes:
    """Sintetiza texto e retorna o mp3 em memória (sem tocar)."""
    voice = get_voice(lang)
    communicate = edge_tts.Communicate(text, voice)
    buf = bytearray()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            buf.extend(chunk["data"])
    return bytes(buf)


def _device_format(device_index: int) -> tuple[int, int]:
    """Retorna (rate, channels) nativos do dispositivo de saída."""
    with PYAUDIO_LOCK:
        pa = pyaudio.PyAudio()
        try:
            d = pa.get_device_info_by_index(device_index)
            rate = int(d["defaultSampleRate"])
            channels = 2 if int(d["maxOutputChannels"]) >= 2 else 1
            return rate, channels
        finally:
            pa.terminate()


def speak_to_device(text: str, lang: str, device_index: int) -> None:
    """Sintetiza e toca o texto (bloqueante) no dispositivo indicado."""
    if not text.strip():
        return
    loop = asyncio.new_event_loop()
    try:
        mp3 = loop.run_until_complete(synthesize_to_mp3_bytes(text, lang))
    finally:
        loop.close()
    rate, channels = _device_format(device_index)
    pcm = mp3_to_pcm(mp3, rate=rate, channels=channels)
    play_pcm_to_device(pcm, device_index, rate, channels)
