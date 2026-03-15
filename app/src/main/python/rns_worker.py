import RNS
import LXMF
import os
import threading
import time
import socket
import base64
from collections import deque

# Patch socket for Android compatibility
if not hasattr(socket, "if_nametoindex"):
    socket.if_nametoindex = lambda name: 0

# KISS Protocol Constants
FEND, FESC, TFEND, TFESC = 0xC0, 0xDB, 0xDC, 0xDD

class BTInterface(RNS.Interfaces.Interface.Interface):
    def __init__(self, owner, name, kt_service):
        super().__init__(owner, name) # Properly call base constructor
        self.kt = kt_service
        self.online = True
        self.HW_MTU = 1064
        self.IN = self.OUT = self.ingress_control = True
        self.mode = RNS.Interfaces.Interface.Interface.MODE_FULL
        
        # Explicitly initialize all RNS housekeeping attributes
        self.rxb = self.txb = self.forwarded_count = self.bitrate = 0
        self.ic_new_time = self.ic_rate_count = self.ic_burst_freq = 0
        self.ic_burst_limit = 5
        self.ic_burst_active = False
        self.ic_burst_start = 0
        self.oa_freq_deque = deque(maxlen=10)
        self.ia_freq_deque = deque(maxlen=10)
        self.announces_held = []
        
        threading.Thread(target=self.read_loop, daemon=True).start()
        RNS.log(f"Sideband-Compatible Interface {name} active.")

    def process_outgoing(self, data):
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
                            if in_frame and len(buffer) > 1:
                                self.owner.inbound(bytes(buffer[1:]), self)
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
known_nodes = {}

def message_received(lxm):
    sender = RNS.prettyhexrep(lxm.source_hash)
    # Sideband check: Is it text or a file/image?
    content = ""
    if isinstance(lxm.content, bytes):
        if lxm.fields and "filename" in lxm.fields:
            content = f"Received File: {lxm.fields["filename"]}"
        else:
            content = "[Binary Data/Image]"
    else:
        content = lxm.content
    
    inbox.append({"sender": sender, "content": content, "time": time.strftime("%H:%M")})

def announce_handler(aspect_filter, data, packet):
    node_hash = RNS.prettyhexrep(packet.destination_hash)
    try:
        name = data.decode("utf-8")
        known_nodes[node_hash] = name
    except:
        known_nodes[node_hash] = "Unknown"

def start(storage_path, kt_service, display_name):
    global lxm_router
    if not os.path.exists(storage_path): os.makedirs(storage_path)
    
    # 1. Initialize Reticulum
    r = RNS.Reticulum(configdir=storage_path)
    RNS.Transport.register_announce_handler(announce_handler)

    # 2. Add Bluetooth Interface
    RNS.Transport.interfaces = [i for i in RNS.Transport.interfaces if i.name != "RNode_BT"]
    RNS.Transport.interfaces.append(BTInterface(r, "RNode_BT", kt_service))
    
    # 3. Identity Setup
    id_dir = os.path.join(storage_path, "storage")
    if not os.path.exists(id_dir): os.makedirs(id_dir)
    id_path = os.path.join(id_dir, "identity")
    identity = RNS.Identity.from_file(id_path) if os.path.exists(id_path) else RNS.Identity()
    if not os.path.exists(id_path): identity.to_file(id_path)
    
    # 4. LXMF Router Setup
    lxm_router = LXMF.LXMRouter(identity=identity, storagepath=storage_path)
    lxm_router.register_delivery_callback(message_received)
    
    # 5. Announce like Sideband
    announce_dest = RNS.Destination(identity, RNS.Destination.IN, RNS.Destination.SINGLE, "lxmf", "delivery")
    announce_dest.announce(app_data=display_name.encode("utf-8"))
    
    return RNS.prettyhexrep(identity.hash)

def send_text(dest_hex, text):
    try:
        dest_hash = bytes.fromhex(dest_hex)
        recipient = RNS.Destination(None, RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery")
        recipient.hash = dest_hash
        lxm = LXMF.LXMessage(recipient, lxm_router.identity, text, title="LXMF Chat")
        lxm_router.handle_outbound(lxm)
        return "Queued"
    except Exception as e: return str(e)

def send_image(dest_hex, img_b64, filename="image.jpg"):
    try:
        dest_hash = bytes.fromhex(dest_hex)
        img_data = base64.b64decode(img_b64)
        recipient = RNS.Destination(None, RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery")
        recipient.hash = dest_hash
        
        # LXMF Image Transmission (as binary content with fields)
        lxm = LXMF.LXMessage(recipient, lxm_router.identity, img_data, title="Attachment")
        lxm.fields["filename"] = filename
        lxm_router.handle_outbound(lxm)
        return f"Image ({len(img_data)} bytes) queued"
    except Exception as e: return str(e)

def get_updates():
    global inbox
    nodes = [f"{v} ({k})" for k, v in known_nodes.items()]
    data = {"inbox": list(inbox), "nodes": nodes}
    inbox = []
    return data