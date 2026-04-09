"""Inicia o watcher de reuniões em background."""
from backend.watcher import MeetingWatcher

if __name__ == "__main__":
    watcher = MeetingWatcher(app_url="http://localhost:8000", poll_interval=3)
    watcher.start()
    print("Watcher de reunioes iniciado.")
    print("Abre o browser automaticamente ao detectar Zoom, Teams, Meet ou Webex.")
    print("Atalho manual: Ctrl+Shift+T")
    print("Ctrl+C para parar.")
    import time
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        watcher.stop()
        print("Watcher encerrado.")
