# tests/test_devices_endpoint.py
from fastapi.testclient import TestClient
from unittest.mock import patch
import backend.main as main


def test_devices_endpoint_shape():
    fake = {
        "inputs": [{"index": 1, "name": "Mic", "rate": 48000, "in_ch": 1, "out_ch": 0}],
        "outputs": [{"index": 7, "name": "CABLE Input", "rate": 48000, "in_ch": 0, "out_ch": 2}],
    }
    with patch.object(main, "list_devices", lambda: fake):
        client = TestClient(main.app)
        r = client.get("/devices")
    assert r.status_code == 200
    body = r.json()
    assert body["inputs"][0]["name"] == "Mic"
    assert body["vbcable"]["index"] == 7
