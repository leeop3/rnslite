import RNS
import LXMF
import os

def initialize(storage_path):
    if not os.path.exists(storage_path):
        os.makedirs(storage_path)
    
    # Changed configpath to configdir to fix the TypeError
    RNS.Reticulum(configdir=storage_path)
    return "RNS Online"

def send_msg(dest_hash_hex, message):
    try:
        # Basic LXMF setup
        return f"Sending to {dest_hash_hex}..."
    except Exception as e:
        return str(e)