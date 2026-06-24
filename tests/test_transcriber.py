import pytest
from unittest.mock import MagicMock, patch

def test_translate_same_language_returns_original():
    from backend.transcriber import translate_text
    result = translate_text("hello world", source="en", target="en")
    assert result == "hello world"

def test_translate_returns_string():
    from backend.transcriber import translate_text
    with patch("backend.transcriber.GoogleTranslator") as mock_cls:
        mock_cls.return_value.translate.return_value = "olá mundo"
        result = translate_text("hello world", source="en", target="pt")
    assert isinstance(result, str)
    assert len(result) > 0


import asyncio
import io
import edge_tts
import av
from backend.transcriber import transcribe_and_translate


def _speech_pcm(text: str, voice: str) -> bytes:
    async def synth():
        comm = edge_tts.Communicate(text, voice)
        buf = bytearray()
        async for c in comm.stream():
            if c["type"] == "audio":
                buf.extend(c["data"])
        return bytes(buf)
    mp3 = asyncio.run(synth())
    container = av.open(io.BytesIO(mp3))
    resampler = av.AudioResampler(format="s16", layout="mono", rate=16000)
    out = bytearray()
    for frame in container.decode(audio=0):
        for r in resampler.resample(frame):
            out.extend(bytes(r.planes[0]))
    return bytes(out)


def test_inbound_detects_english_and_translates_to_pt():
    pcm = _speech_pcm("Good morning, how are you today?", "en-US-JennyNeural")
    results = []
    transcribe_and_translate(
        pcm, source_lang="en", target_lang="pt", speaker="Outro",
        on_result=lambda sp, o, t, dl: results.append((sp, o, t, dl)),
        detect=True, drop_langs=("pt",),
    )
    assert len(results) == 1
    assert results[0][3] == "en"          # detected_lang
    assert results[0][2].strip() != ""    # tradução PT não vazia


def test_inbound_drops_portuguese_echo():
    pcm = _speech_pcm("Olá, tudo bem com você hoje?", "pt-BR-FranciscaNeural")
    results = []
    transcribe_and_translate(
        pcm, source_lang="en", target_lang="pt", speaker="Outro",
        on_result=lambda sp, o, t, dl: results.append((sp, o, t, dl)),
        detect=True, drop_langs=("pt",),
    )
    assert results == []  # eco em PT descartado
