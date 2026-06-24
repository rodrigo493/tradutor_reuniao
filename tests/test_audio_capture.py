from backend.audio import AudioCapture


def test_pause_resume_flags_default_running():
    cap = AudioCapture()
    assert cap.loopback_paused is False
    cap.pause_loopback()
    assert cap.loopback_paused is True
    cap.resume_loopback()
    assert cap.loopback_paused is False


def test_accepts_device_indices():
    cap = AudioCapture(mic_index=1, loopback_index=9)
    assert cap.mic_index == 1
    assert cap.loopback_index == 9


def test_pause_loopback_drains_spk_queue():
    cap = AudioCapture()
    cap.spk_queue.put(b"x")
    cap.pause_loopback()
    assert cap.spk_queue.qsize() == 0
