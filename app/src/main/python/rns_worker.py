import RNS
import LXMF
import os
import threading
import time
import socket
import base64
from collections import deque

# Patch socket to prevent Android if_nametoindex crash
if not hasattr(socket, "if_nametoindex"):
    socket.if_nametoindex = lambda name: 0

FEND, FESC, TFEND, TFESC = 0xC0, 0xDB, 0xDC, 0xDD

class BTInterface(RNS.Interfaces.Interface.Interface):
    def __init__(self, owner, name, kt_service):
        self.owner, self.name, self.kt = owner, name, kt_service
        self.online = self.IN = self.OUT = self.ingress_control = True
        self.HW_MTU, self.forwarded_count, self.bitrate, self.rxb, self.txb = 1024, 0, 0, 0, 0
        self.mode = RNS.Interfaces.Interface.Interface.MODE_FULL
        self.oa_freq_deque = deque(maxlen=10)
        self.ia_freq_deque = deque(maxlen=10)
        self.announces_held = []
        self.announce_cap = 20
        threading.Thread(target=self.read_loop, daemon=True).start()

    def process_outgoing(self, data):
        self.send_bin(data)

    def send_bin(self, data):
        self.txb += len(data)
        frame = bytearray([FEND, 0x00])
        for byte in data:
            if byte == FEND: frame.extend([FESC, TFEND])
            elif byte == FESC: frame.extend([FESC, TFESC])
            else: frame.append(byte)
        frame.append(FEND)
        self.kt.write(bytes(frame))

    def read_loop(self):
        buffer, in_frame, escape = bytearray(), False, False
        while self.online:
            try:
                data = self.kt.read()
                if data:
                    self.rxb += len(data)
                    for byte in data:
                        if byte == FEND:
                            if in_frame and len(buffer) > 1: self.owner.inbound(bytes(buffer[1:]), self)
                            buffer, in_frame = bytearray(), True
                        elif in_frame:
                            if byte == FESC: escape = True
                            else:
                                if escape:
                                    if byte == TFEND: buffer.append(FEND)
                                    elif byte == TFESC: buffer.append(FESC)
                                    escape = False
                                else: buffer.append(byte)
                else: time.sleep(0.01)
            except: time.sleep(1)

lxm_router = None
inbox = []
known_nodes = set()

def message_received(lxm):
    sender = RNS.prettyhexrep(lxm.source_hash)
    content = lxm.content.decode("utf-8") if isinstance(lxm.content, bytes) else lxm.content
    inbox.append({"sender": sender, "content": content, "time": time.strftime("%H:%M")})

def announce_handler(aspect_filter, data, packet):
    node_hash = RNS.prettyhexrep(packet.destination_hash)
    known_nodes.add(node_hash)

def start(storage_path, kt_service, display_name):
    global lxm_router
    if not os.path.exists(storage_path): os.makedirs(storage_path)
    config_path = os.path.join(storage_path, "config")
    with open(config_path, "w") as f:
        f.write("[reticulum]\nenable_auto_interface = No\n")
    
    r = RNS.Reticulum(configdir=storage_path)
    bt_if = BTInterface(r, "RNode_BT", kt_service)
    RNS.Transport.interfaces.append(bt_if)
    
    id_dir = os.path.join(storage_path, "storage")
    if not os.path.exists(id_dir): os.makedirs(id_dir)
    id_path = os.path.join(id_dir, "identity")
    identity = RNS.Identity.from_file(id_path) if os.path.exists(id_path) else RNS.Identity()
    if not os.path.exists(id_path): identity.to_file(id_path)
    
    lxm_router = LXMF.LXMRouter(identity=identity, storagepath=storage_path)
    lxm_router.register_delivery_callback(message_received)
    
    # FIX: register_announce_handler belongs to RNS.Transport
    RNS.Transport.register_announce_handler(announce_handler)
    
    announce_dest = RNS.Destination(identity, RNS.Destination.IN, RNS.Destination.SINGLE, "lxmf", "delivery")
    announce_dest.announce(app_data=display_name.encode("utf-8"))
    return RNS.prettyhexrep(identity.hash)

def send_lxm(dest_hex, text):
    try:
        dest_hash = bytes.fromhex(dest_hex)
        recipient = RNS.Destination(None, RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery")
        recipient.hash = dest_hash
        lxm = LXMF.LXMessage(recipient, lxm_router.identity, text)
        lxm_router.handle_outbound(lxm)
        return "Queued"
    except Exception as e: return str(e)

def get_updates():
    global inbox
    data = {"inbox": list(inbox), "nodes": list(known_nodes)}
    inbox = []
    return data