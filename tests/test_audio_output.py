import asyncio

import pytest

import edge_tts

from backend.audio_output import mp3_to_pcm

pytestmark = pytest.mark.integration


@pytest.fixture(scope="session")
def sample_mp3() -> bytes:
    """Generate sample MP3 once per session via edge-tts."""
    async def _synth() -> bytes:
        comm = edge_tts.Communicate("Hello world, this is a test.", "en-US-JennyNeural")
        buf = bytearray()
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                buf.extend(chunk["data"])
        return bytes(buf)
    return asyncio.run(_synth())


def test_mp3_to_pcm_produces_pcm_at_requested_rate(sample_mp3: bytes) -> None:
    pcm = mp3_to_pcm(sample_mp3, rate=48000, channels=2)
    assert isinstance(pcm, bytes)
    # ~1.5s de fala a 48kHz estéreo int16 => muito mais que 10k bytes
    assert len(pcm) > 10000
    # estéreo int16 => múltiplo de 4 bytes por frame
    assert len(pcm) % 4 == 0


def test_mp3_to_pcm_mono_frame_alignment(sample_mp3: bytes) -> None:
    pcm = mp3_to_pcm(sample_mp3, rate=16000, channels=1)
    assert len(pcm) % 2 == 0
    assert len(pcm) > 5000
