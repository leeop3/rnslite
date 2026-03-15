import sys
import os
import threading
import time
import socket
import base64

# --- THE TRICK ---
# Reticulum has a check that prevents using the standard RNodeInterface on Android.
# We "mock" the platform to bypass this so we can use the official driver.
import platform
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

lxm_router = None
inbox = []
known_nodes = {}
log_buffer = []

def log_hook(msg):
    log_buffer.append(msg)
    if len(log_buffer) > 50: log_buffer.pop(0)

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
    RNS.log_hooks.add(log_hook)
    
    if not os.path.exists(storage_path): os.makedirs(storage_path)
    config_path = os.path.join(storage_path, "config")
    with open(config_path, "w") as f:
        f.write("[reticulum]\nenable_auto_interface = No\n")
    
    # 1. Start RNS
    r = RNS.Reticulum(configdir=storage_path)
    RNS.Transport.register_announce_handler(announce_handler)

    # 2. Use the OFFICIAL RNodeInterface driver
    # This sends the initialization commands Sideband uses.
    from RNS.Interfaces.RNodeInterface import RNodeInterface
    
    rnode_config = {
        "name": "RNode_BT",
        "device": BTSerialProxy(kt_service),
        "frequency": 0, # Use hardware default
        "bandwidth": 0,
        "txpower": 0,
        "sf": 0,
        "cr": 0,
        "flow_control": False
    }
    
    try:
        # This will now succeed because we "tricked" the system check
        rnode_if = RNodeInterface(r, rnode_config)
        RNS.Transport.interfaces.append(rnode_if)
        RNS.log("Official RNode driver initialized over BT.")
    except Exception as e:
        RNS.log("Driver Error: " + str(e))

    # 3. Identity & LXMF
    id_dir = os.path.join(storage_path, "storage")
    if not os.path.exists(id_dir): os.makedirs(id_dir)
    id_path = os.path.join(id_dir, "identity")
    identity = RNS.Identity.from_file(id_path) if os.path.exists(id_path) else RNS.Identity()
    if not os.path.exists(id_path): identity.to_file(id_path)
    
    lxm_router = LXMF.LXMRouter(identity=identity, storagepath=storage_path)
    lxm_router.register_delivery_callback(message_received)
    
    # Send Announce
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