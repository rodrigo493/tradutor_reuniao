import threading

# PyAudio/PortAudio + WASAPI segfaults when PyAudio() is constructed or a stream
# is opened from multiple threads concurrently (observed on Python 3.14). Every
# PyAudio() construction and stream open across the app must be serialized
# through this single lock. Reads/writes/closes do not need it.
PYAUDIO_LOCK = threading.RLock()
