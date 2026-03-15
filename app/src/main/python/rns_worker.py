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

class BTInterface(RNS.Interfaces.Interface.Interface):
    def __init__(self, owner, name, kt_service):
        super().__init__(owner, name)
        self.kt = kt_service
        self.online = True
        self.HW_MTU = 1024
        threading.Thread(target=self.read_loop, daemon=True).start()

    def send_bin(self, data):
        # Manually wrap data in KISS frame (FEND + CMD + DATA + FEND)
        # 0x00 is the KISS "Data Frame" command
        frame = bytearray([FEND, 0x00])
        for byte in data:
            if byte == FEND:
                frame.append(FESC)
                frame.append(TFEND)
            elif byte == FESC:
                frame.append(FESC)
                frame.append(TFESC)
            else:
                frame.append(byte)
        frame.append(FEND)
        self.kt.write(bytes(frame))

    def read_loop(self):
        in_frame = False
        escape = False
        buffer = bytearray()
        
        while self.online:
            data = self.kt.read()
            if data:
                for byte in data:
                    if byte == FEND:
                        if in_frame and len(buffer) > 1:
                            # Strip the KISS command byte (first byte) and process
                            self.owner.inbound(bytes(buffer[1:]), self)
                        buffer = bytearray()
                        in_frame = True
                    elif in_frame:
                        if byte == FESC:
                            escape = True
                        else:
                            if escape:
                                if byte == TFEND: buffer.append(FEND)
                                elif byte == TFESC: buffer.append(FESC)
                                escape = False
                            else:
                                buffer.append(byte)
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
    
    # Use base Interface to bypass Android-specific hardware checks
    bt_if = BTInterface(r, "RNode_BT", kt_service)
    r.interfaces.append(bt_if)
    
    id_path = os.path.join(storage_path, "storage", "identity")
    identity = RNS.Identity.from_file(id_path) if os.path.exists(id_path) else RNS.Identity()
    if not os.path.exists(id_path): identity.to_file(id_path)
    
    lxm_router = LXMF.LXMRouter(identity=identity, storagepath=storage_path)
    lxm_router.register_delivery_callback(message_received)
    
    # Trigger an announcement so other users see us
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