from backend.devices import find_vbcable


def test_find_vbcable_matches_cable_input():
    outputs = [
        {"index": 3, "name": "Headphones (Realtek)", "rate": 48000, "in_ch": 0, "out_ch": 2},
        {"index": 7, "name": "CABLE Input (VB-Audio Virtual Cable)", "rate": 48000, "in_ch": 0, "out_ch": 2},
    ]
    found = find_vbcable(outputs)
    assert found is not None
    assert found["index"] == 7


def test_find_vbcable_returns_none_when_absent():
    outputs = [{"index": 3, "name": "Headphones (Realtek)", "rate": 48000, "in_ch": 0, "out_ch": 2}]
    assert find_vbcable(outputs) is None
