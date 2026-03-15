import RNS
import LXMF
import os
import threading
import time
import socket

# Patch socket to prevent Android if_nametoindex crash
if not hasattr(socket, "if_nametoindex"):
    socket.if_nametoindex = lambda name: 0

# KISS Protocol Constants
FEND = 0xC0
FESC = 0xDB
TFEND = 0xDC
TFESC = 0xDD
CMD_DATA = 0x00

class BTInterface(RNS.Interfaces.Interface.Interface):
    def __init__(self, owner, name, kt_service):
        # Fix: Manually set properties instead of relying on super().__init__ 
        # which is causing the positional argument crash in 1.1.4
        self.owner = owner
        self.name = name
        self.kt = kt_service
        self.online = True
        self.HW_MTU = 1024
        self.IN = False
        self.OUT = False
        self.forwarded_count = 0
        self.bitrate = 0
        
        # Start the read loop
        threading.Thread(target=self.read_loop, daemon=True).start()
        RNS.log(f"BTInterface {name} initialized")

    def send_bin(self, data):
        # KISS wrapping: FEND + CMD + DATA + FEND
        frame = bytearray([FEND, CMD_DATA])
        for byte in data:
            if byte == FEND: frame.extend([FESC, TFEND])
            elif byte == FESC: frame.extend([FESC, TFESC])
            else: frame.append(byte)
        frame.append(FEND)
        self.kt.write(bytes(frame))

    def read_loop(self):
        buffer = bytearray()
        in_frame = False
        escape = False
        while self.online:
            data = self.kt.read()
            if data:
                for byte in data:
                    if byte == FEND:
                        if in_frame and len(buffer) > 1:
                            # Process frame (skip command byte)
                            self.owner.inbound(bytes(buffer[1:]), self)
                        buffer = bytearray()
                        in_frame = True
                    elif in_frame:
                        if byte == FESC: escape = True
                        else:
                            if escape:
                                if byte == TFEND: buffer.append(FEND)
                                elif byte == TFESC: buffer.append(FESC)
                                escape = False
                            else: buffer.append(byte)
            else:
                time.sleep(0.01)

lxm_router = None
received_messages = []

def message_received(lxm):
    sender = RNS.prettyhexrep(lxm.source_hash)
    content = lxm.content.decode("utf-8") if isinstance(lxm.content, bytes) else lxm.content
    received_messages.append({"sender": sender, "content": content})

def start(storage_path, kt_service):
    global lxm_router
    if not os.path.exists(storage_path): os.makedirs(storage_path)
    
    config_path = os.path.join(storage_path, "config")
    with open(config_path, "w") as f:
        f.write("[reticulum]\nenable_auto_interface = No\n")
    
    r = RNS.Reticulum(configdir=storage_path)
    
    # Instantiate fixed interface
    bt_if = BTInterface(r, "RNode_BT", kt_service)
    r.interfaces.append(bt_if)
    
    id_path = os.path.join(storage_path, "storage", "identity")
    identity = RNS.Identity.from_file(id_path) if os.path.exists(id_path) else RNS.Identity()
    if not os.path.exists(id_path): identity.to_file(id_path)
    
    lxm_router = LXMF.LXMRouter(identity=identity, storagepath=storage_path)
    lxm_router.register_delivery_callback(message_received)
    
    # Send RNS Announce
    announce_dest = RNS.Destination(identity, RNS.Destination.IN, RNS.Destination.SINGLE, "lxmf", "delivery")
    announce_dest.announce()
    
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