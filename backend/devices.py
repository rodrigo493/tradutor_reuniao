from typing import Optional
import pyaudiowpatch as pyaudio


def list_devices() -> dict:
    """Lista dispositivos de entrada e saída disponíveis."""
    pa = pyaudio.PyAudio()
    inputs, outputs = [], []
    try:
        for i in range(pa.get_device_count()):
            d = pa.get_device_info_by_index(i)
            entry = {
                "index": int(d["index"]),
                "name": str(d["name"]),
                "rate": int(d["defaultSampleRate"]),
                "in_ch": int(d["maxInputChannels"]),
                "out_ch": int(d["maxOutputChannels"]),
            }
            if entry["in_ch"] > 0:
                inputs.append(entry)
            if entry["out_ch"] > 0:
                outputs.append(entry)
    finally:
        pa.terminate()
    return {"inputs": inputs, "outputs": outputs}


def find_vbcable(outputs: list[dict]) -> Optional[dict]:
    """Retorna o dispositivo de saída do VB-Cable, ou None se não instalado."""
    for d in outputs:
        if "cable" in d["name"].lower():
            return d
    return None
