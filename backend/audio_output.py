import io
import logging

import av  # vem junto com faster-whisper
import pyaudiowpatch as pyaudio

from backend.audio_lock import PYAUDIO_LOCK

_log = logging.getLogger(__name__)


def mp3_to_pcm(mp3: bytes, rate: int, channels: int) -> bytes:
    """Decodifica mp3 para PCM int16 packed, reamostrado para rate/channels."""
    if not mp3:
        raise ValueError("mp3 input is empty")
    if channels < 1:
        raise ValueError(f"channels must be >= 1, got {channels}")

    layout = "stereo" if channels >= 2 else "mono"
    try:
        with av.open(io.BytesIO(mp3)) as container:
            resampler = av.AudioResampler(format="s16", layout=layout, rate=rate)
            out = bytearray()
            for frame in container.decode(audio=0):
                for resampled in resampler.resample(frame):
                    out.extend(bytes(resampled.planes[0]))
            # flush do resampler
            for resampled in resampler.resample(None):
                out.extend(bytes(resampled.planes[0]))
            return bytes(out)
    except av.error.InvalidDataError as exc:
        raise ValueError(f"Failed to decode MP3 data ({len(mp3)} bytes)") from exc


def play_pcm_to_device(pcm: bytes, device_index: int, rate: int, channels: int) -> None:
    """Toca PCM int16 bloqueante no dispositivo de saída indicado."""
    with PYAUDIO_LOCK:
        pa = pyaudio.PyAudio()
        stream = pa.open(
            format=pyaudio.paInt16,
            channels=channels,
            rate=rate,
            output=True,
            output_device_index=device_index,
        )
    try:
        try:
            stream.write(pcm)
        finally:
            stream.stop_stream()
            stream.close()
    finally:
        pa.terminate()
