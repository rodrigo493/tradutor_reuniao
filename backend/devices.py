from typing import Optional
import pyaudiowpatch as pyaudio

from backend.audio_lock import PYAUDIO_LOCK


def list_devices() -> dict:
    """Lista dispositivos de entrada e saída disponíveis."""
    inputs, outputs = [], []
    with PYAUDIO_LOCK:
        pa = pyaudio.PyAudio()
    try:
        for i in range(pa.get_device_count()):
            d = pa.get_device_info_by_index(i)
            try:
                host_api = str(pa.get_host_api_info_by_index(d["hostApi"])["name"])
            except Exception:
                host_api = ""
            entry = {
                "index": int(d["index"]),
                "name": str(d["name"]),
                "rate": int(d["defaultSampleRate"]),
                "in_ch": int(d["maxInputChannels"]),
                "out_ch": int(d["maxOutputChannels"]),
                "host_api": host_api,
            }
            if entry["in_ch"] > 0:
                inputs.append(entry)
            if entry["out_ch"] > 0:
                outputs.append(entry)
    finally:
        pa.terminate()
    return {"inputs": inputs, "outputs": outputs}


def index_by_name(devices: list[dict]) -> dict:
    """Mapeia nome -> índice preferindo a instância WASAPI (roteamento confiável
    por dispositivo no Windows; MME costuma cair no dispositivo padrão). Cai para
    o primeiro encontrado quando não há WASAPI."""
    result: dict = {}
    chosen_api: dict = {}
    for d in devices:
        name = d["name"]
        is_wasapi = d.get("host_api") == "Windows WASAPI"
        if name not in result or (is_wasapi and chosen_api.get(name) != "Windows WASAPI"):
            result[name] = d["index"]
            chosen_api[name] = d.get("host_api")
    return result


def find_vbcable(outputs: list[dict]) -> Optional[dict]:
    """Retorna o dispositivo de saída do VB-Cable, ou None se não instalado."""
    wasapi = [d for d in outputs if "cable" in d["name"].lower() and d.get("host_api") == "Windows WASAPI"]
    if wasapi:
        return wasapi[0]
    for d in outputs:
        if "cable" in d["name"].lower():
            return d
    return None
