import sys
import subprocess
import pytest


@pytest.mark.skipif(sys.platform != "win32", reason="WASAPI/PyAudio só no Windows")
def test_concurrent_capture_does_not_segfault():
    """AudioCapture abre mic + loopback em duas threads. No Python 3.14 isso
    causava segfault (exit 139) por abertura concorrente de PyAudio/WASAPI; o
    lock global em backend.audio_lock serializa a abertura. Rodamos em
    subprocesso porque um segfault derruba o interpretador inteiro."""
    code = (
        "import time\n"
        "from backend.audio import AudioCapture\n"
        "cap = AudioCapture()\n"
        "cap.start()\n"
        "time.sleep(3)\n"
        "cap.stop()\n"
        "time.sleep(0.5)\n"
        "print('OK')\n"
    )
    r = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True, text=True, timeout=60,
    )
    assert r.returncode == 0, (
        f"captura concorrente crashou (exit {r.returncode}): {r.stderr[-400:]}"
    )
