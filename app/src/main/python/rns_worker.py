import RNS
import LXMF
import os
import threading
import time
import socket

# Patch socket to prevent Android if_nametoindex crash
if not hasattr(socket, "if_nametoindex"):
    socket.if_nametoindex = lambda name: 0

class BTSerialProxy:
    def __init__(self, kt_service):
        self.kt = kt_service
    def read(self, size=1):
        return self.kt.read()
    def write(self, data):
        self.kt.write(data)
    def close(self):
        self.kt.close()
    def flush(self):
        pass

lxm_router = None
received_messages = []

def message_received(lxm):
    sender = RNS.prettyhexrep(lxm.source_hash)
    content = lxm.content.decode("utf-8") if isinstance(lxm.content, bytes) else lxm.content
    received_messages.append({"sender": sender, "content": content})

def start(storage_path, kt_service):
    global lxm_router
    
    if not os.path.exists(storage_path):
        os.makedirs(storage_path)
    
    # Force disable AutoInterface in config
    config_path = os.path.join(storage_path, "config")
    with open(config_path, "w") as f:
        f.write("[reticulum]\nenable_auto_interface = No\n")
    
    # 1. Start RNS with explicit path
    r = RNS.Reticulum(configdir=storage_path)
    
    # 2. Setup Bluetooth Interface via Dictionary Configuration
    from RNS.Interfaces.RNodeInterface import RNodeInterface
    rnode_config = {
        "name": "RNode_BT",
        "device": BTSerialProxy(kt_service),
        "frequency": 0,
        "bandwidth": 0,
        "txpower": 0,
        "sf": 0,
        "cr": 0
    }
    rnode_if = RNodeInterface(r, rnode_config)
    r.interfaces.append(rnode_if)
    
    # 3. Setup LXMF
    id_path = os.path.join(storage_path, "storage", "identity")
    identity = RNS.Identity.from_file(id_path) if os.path.exists(id_path) else RNS.Identity()
    if not os.path.exists(id_path): identity.to_file(id_path)
    
    lxm_router = LXMF.LXMRouter(identity=identity, storagepath=storage_path)
    lxm_router.register_delivery_callback(message_received)
    
    return RNS.prettyhexrep(identity.hash)

def send_txt(dest_hex, text):
    try:
        dest_hash = bytes.fromhex(dest_hex)
        recipient = RNS.Destination(None, RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery")
        recipient.hash = dest_hash
        lxm = LXMF.LXMessage(recipient, lxm_router.identity, text)
        lxm_router.handle_outbound(lxm)
        return "Queued"
    except Exception as e: return str(e)

def get_inbox():
    global received_messages
    res = list(received_messages)
    received_messages = []
    return res