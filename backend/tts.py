import asyncio
import tempfile
import os
import threading
import edge_tts

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
