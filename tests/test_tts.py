import asyncio
from backend.tts import synthesize_to_mp3_bytes, get_voice


def test_get_voice_known_and_fallback():
    assert get_voice("en") == "en-US-JennyNeural"
    assert get_voice("pt") == "pt-BR-FranciscaNeural"
    assert get_voice("xx") == "pt-BR-FranciscaNeural"  # fallback


def test_synthesize_to_mp3_bytes_nonempty():
    mp3 = asyncio.run(synthesize_to_mp3_bytes("Olá, teste de voz.", "pt"))
    assert isinstance(mp3, bytes)
    assert len(mp3) > 1000
