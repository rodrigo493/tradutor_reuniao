import time
import webbrowser
import psutil
import threading
from typing import Optional

try:
    import pygetwindow as gw
    HAS_GETWINDOW = True
except ImportError:
    HAS_GETWINDOW = False

try:
    import keyboard
    HAS_KEYBOARD = True
except ImportError:
    HAS_KEYBOARD = False

MEETING_PROCESSES = {
    "zoom": "Zoom",
    "ms-teams": "Microsoft Teams",
    "teams": "Microsoft Teams",
    "webex": "Webex",
    "slack": "Slack",
}

MEET_WINDOW_KEYWORDS = ["meet.google.com", "Google Meet", "- Meet"]
APP_URL = "http://localhost:8000"
POLL_INTERVAL = 3  # segundos

def is_meeting_running() -> bool:
    """Retorna True se qualquer app de reunião conhecido estiver rodando."""
    running = {p.name().lower() for p in psutil.process_iter(["name"])}
    for proc in MEETING_PROCESSES:
        if any(proc in r for r in running):
            return True
    # Verifica títulos de janela para Google Meet
    if HAS_GETWINDOW:
        try:
            windows = gw.getAllTitles()
            for title in windows:
                if any(kw in title for kw in MEET_WINDOW_KEYWORDS):
                    return True
        except Exception:
            pass
    return False

class MeetingWatcher:
    def __init__(self, app_url: str = APP_URL, poll_interval: int = POLL_INTERVAL):
        self.app_url = app_url
        self.poll_interval = poll_interval
        self._running = False
        self._meeting_open = False
        self._thread: Optional[threading.Thread] = None

    def _open_app(self):
        if not self._meeting_open:
            webbrowser.open(self.app_url)
            self._meeting_open = True
            print(f"Reunião detectada — abrindo {self.app_url}")

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._watch_loop, daemon=True)
        self._thread.start()
        if HAS_KEYBOARD:
            keyboard.add_hotkey("ctrl+shift+t", self._open_app)
            print("Watcher iniciado. Ctrl+Shift+T para abrir manualmente.")

    def stop(self):
        self._running = False

    def _watch_loop(self):
        was_running = False
        while self._running:
            now_running = is_meeting_running()
            if now_running and not was_running:
                self._open_app()
            elif not now_running and was_running:
                self._meeting_open = False
                print("Reunião encerrada.")
            was_running = now_running
            time.sleep(self.poll_interval)


if __name__ == "__main__":
    watcher = MeetingWatcher()
    watcher.start()
    print("Monitorando reuniões... Ctrl+C para parar.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        watcher.stop()
        print("Watcher encerrado.")
