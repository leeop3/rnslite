import sys
import os
import threading
import time
import socket
import base64
import platform

# --- THE TRICK ---
# Bypass Android detection to use the official Mark Qvist RNode driver
platform.system = lambda: "Linux"

# Patch socket for Android compatibility
if not hasattr(socket, "if_nametoindex"):
    socket.if_nametoindex = lambda name: 0

import RNS
import LXMF

# Proxy to make Kotlin BT look like a Serial Port for the official driver
class BTSerialProxy:
    def __init__(self, kt_service):
        self.kt = kt_service
        self.is_open = True
        self.baudrate = 115200
        self.timeout = 0
    def read(self, size=1):
        return self.kt.read()
    def write(self, data):
        return self.kt.write(data)
    def close(self):
        self.is_open = False
    def flush(self):
        pass
    def isOpen(self):
        return self.is_open
    @property
    def in_waiting(self):
        # Official driver uses this to check for data
        return 1

lxm_router = None
inbox = []
known_nodes = {}
log_buffer = []

def log_hook(msg):
    log_buffer.append(str(msg))
    if len(log_buffer) > 50: log_buffer.pop(0)

# --- FIX: Monkey-patch RNS.log because log_hooks doesn't exist in 1.1.4 ---
old_rns_log = RNS.log
def custom_rns_log(msg, level=3):
    log_hook(msg)
    old_rns_log(msg, level)
RNS.log = custom_rns_log

def message_received(lxm):
    sender = RNS.prettyhexrep(lxm.source_hash)
    content = lxm.content.decode("utf-8") if isinstance(lxm.content, bytes) else lxm.content
    inbox.append({"sender": sender, "content": content, "time": time.strftime("%H:%M")})

def announce_handler(aspect_filter, data, packet):
    node_hash = RNS.prettyhexrep(packet.destination_hash)
    try:
        name = data.decode("utf-8")
        known_nodes[node_hash] = name
    except:
        known_nodes[node_hash] = "Node " + node_hash[:6]

def start(storage_path, kt_service, display_name):
    global lxm_router
    
    if not os.path.exists(storage_path): os.makedirs(storage_path)
    config_path = os.path.join(storage_path, "config")
    with open(config_path, "w") as f:
        f.write("[reticulum]\nenable_auto_interface = No\n")
    
    # 1. Start RNS
    r = RNS.Reticulum.get_instance()
    if r is None:
        r = RNS.Reticulum(configdir=storage_path)
        RNS.Transport.register_announce_handler(announce_handler)

    # 2. Use the OFFICIAL RNodeInterface
    RNS.Transport.interfaces = [i for i in RNS.Transport.interfaces if i.name != "RNode_BT"]
    
    rnode_config = {
        "name": "RNode_BT",
        "device": BTSerialProxy(kt_service),
        "frequency": 0,
        "bandwidth": 0,
        "txpower": 0,
        "sf": 0,
        "cr": 0,
        "flow_control": False
    }
    
    try:
        from RNS.Interfaces.RNodeInterface import RNodeInterface
        rnode_if = RNodeInterface(r, rnode_config)
        RNS.Transport.interfaces.append(rnode_if)
        RNS.log("Official Mark Qvist RNode driver loaded.")
    except Exception as e:
        RNS.log("Driver Failure: " + str(e))

    # 3. Identity & LXMF
    id_dir = os.path.join(storage_path, "storage")
    if not os.path.exists(id_dir): os.makedirs(id_dir)
    id_path = os.path.join(id_dir, "identity")
    identity = RNS.Identity.from_file(id_path) if os.path.exists(id_path) else RNS.Identity()
    if not os.path.exists(id_path): identity.to_file(id_path)
    
    if lxm_router is None:
        lxm_router = LXMF.LXMRouter(identity=identity, storagepath=storage_path)
        lxm_router.register_delivery_callback(message_received)
    
    # Announce
    announce_dest = RNS.Destination(identity, RNS.Destination.IN, RNS.Destination.SINGLE, "lxmf", "delivery")
    announce_dest.announce(app_data=display_name.encode("utf-8"))
    
    return RNS.prettyhexrep(identity.hash)

def send_text(dest_hex, text):
    try:
        dest_hash = bytes.fromhex(dest_hex)
        recp_id = RNS.Identity.recall(dest_hash)
        recipient = RNS.Destination(recp_id, RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery")
        if recp_id is None:
            recipient.hash = dest_hash
            RNS.Transport.request_path(dest_hash)
            return "Peer unknown. Path requested."
        
        lxm = LXMF.LXMessage(recipient, lxm_router.identity, text, title="RNS Lite")
        lxm_router.handle_outbound(lxm)
        return "Queued"
    except Exception as e: return str(e)

def get_updates():
    global inbox, log_buffer
    nodes = [f"{v} ({k})" for k, v in known_nodes.items()]
    data = {"inbox": list(inbox), "nodes": nodes, "logs": list(log_buffer)}
    inbox = []
    log_buffer = []
    return data