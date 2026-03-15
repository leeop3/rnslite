import json
import os
import threading

_CONFIG_PATH = "/data/data/com.leeop3.rnslite/files/rnode_config.json"
_lock = threading.Lock()

DEFAULTS = {
    "frequency": 433025000,
    "bandwidth":     31250,
    "txpower":          17,
    "sf":                8,
    "cr":                6,
}

_config: dict = {}

def _load():
    global _config
    try:
        if os.path.exists(_CONFIG_PATH):
            with open(_CONFIG_PATH, "r") as f:
                loaded = json.load(f)
            _config = {**DEFAULTS, **loaded}
        else:
            _config = dict(DEFAULTS)
    except Exception as e:
        _config = dict(DEFAULTS)

def _save():
    try:
        os.makedirs(os.path.dirname(_CONFIG_PATH), exist_ok=True)
        with open(_CONFIG_PATH, "w") as f:
            json.dump(_config, f, indent=2)
    except Exception as e:
        pass

def get() -> dict:
    with _lock:
        return dict(_config)

def save(frequency: int, bandwidth: int, txpower: int, sf: int, cr: int) -> str:
    errors = []
    if not (400_000_000 <= frequency <= 510_000_000):
        errors.append("Frequency must be between 400-510 MHz")
    if bandwidth not in (7800, 10400, 15600, 20800, 31250, 41700, 62500, 125000, 250000, 500000):
        errors.append("Invalid bandwidth value")
    if not (0 <= txpower <= 17):
        errors.append("TX power must be 0-17 dBm")
    if not (6 <= sf <= 12):
        errors.append("Spreading factor must be 6-12")
    if not (5 <= cr <= 8):
        errors.append("Coding rate must be 5-8")
    if errors:
        return "Error: " + "; ".join(errors)

    with _lock:
        _config["frequency"] = int(frequency)
        _config["bandwidth"]  = int(bandwidth)
        _config["txpower"]    = int(txpower)
        _config["sf"]         = int(sf)
        _config["cr"]         = int(cr)
        _save()
    return "OK"

_load()