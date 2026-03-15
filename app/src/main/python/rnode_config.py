import json
import os

PATH = "/data/data/com.leeop3.rnslite/files/rnode_config.json"

def get():
    if os.path.exists(PATH):
        with open(PATH, "r") as f: return json.load(f)
    # Default settings (915MHz, 125kHz BW, SF7)
    return {"frequency": 915000000, "bandwidth": 125000, "txpower": 7, "sf": 7, "cr": 5}

def save(f, b, p, s, c):
    cfg = {"frequency": f, "bandwidth": b, "txpower": p, "sf": s, "cr": c}
    with open(PATH, "w") as f: json.dump(cfg, f)
    return "OK"