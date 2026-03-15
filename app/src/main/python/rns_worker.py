import RNS
import LXMF
import os
import threading
import time
import socket
import base64

if not hasattr(socket, "if_nametoindex"):
    socket.if_nametoindex = lambda name: 0

# KISS Protocol Constants
FEND, FESC, TFEND, TFESC = 0xC0, 0xDB, 0xDC, 0xDD

class BTInterface(RNS.Interfaces.Interface.Interface):
    def __init__(self, owner, name, kt_service):
        self.owner, self.name, self.kt = owner, name, kt_service
        self.online = True
        self.IN = self.OUT = self.ingress_control = True
        self.forwarded_count = self.bitrate = self.rxb = self.txb = 0
        self.mode = RNS.Interfaces.Interface.Interface.MODE_FULL
        threading.Thread(target=self.read_loop, daemon=True).start()

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

lxm_router = None
inbox = []
known_nodes = {} # {hash: {name: str, last_seen: time}}

def message_received(lxm):
    sender_hash = RNS.prettyhexrep(lxm.source_hash)
    content = lxm.content.decode("utf-8") if isinstance(lxm.content, bytes) else lxm.content
    
    # Extract image if present (Sideband format)
    image_b64 = None
    if lxm.fields and "image" in lxm.fields:
        image_b64 = base64.b64encode(lxm.fields["image"]).decode("utf-8")
    
    inbox.append({
        "sender": sender_hash,
        "content": content,
        "image": image_b64,
        "time": time.strftime("%H:%M")
    })

def announce_handler(aspect_filter, data, packet):
    # Discovery logic like Sideband
    node_hash = RNS.prettyhexrep(packet.destination_hash)
    if node_hash not in known_nodes:
        known_nodes[node_hash] = {"last_seen": time.time()}
        RNS.log(f"Discovered node: {node_hash}")

def start(storage_path, kt_service, display_name):
    global lxm_router
    if not os.path.exists(storage_path): os.makedirs(storage_path)
    with open(os.path.join(storage_path, "config"), "w") as f:
        f.write("[reticulum]\nenable_auto_interface = No\n")
    
    r = RNS.Reticulum(configdir=storage_path)
    RNS.Transport.interfaces.append(BTInterface(r, "RNode_BT", kt_service))
    
    id_path = os.path.join(storage_path, "storage", "identity")
    if not os.path.exists(os.path.dirname(id_path)): os.makedirs(os.path.dirname(id_path))
    identity = RNS.Identity.from_file(id_path) if os.path.exists(id_path) else RNS.Identity()
    if not os.path.exists(id_path): identity.to_file(id_path)
    
    lxm_router = LXMF.LXMRouter(identity=identity, storagepath=storage_path)
    lxm_router.register_delivery_callback(message_received)
    
    # Discovery listener
    r.register_announce_handler(announce_handler)
    
    # Announce with Display Name (Sideband style)
    announce_dest = RNS.Destination(identity, RNS.Destination.IN, RNS.Destination.SINGLE, "lxmf", "delivery")
    announce_dest.announce(app_data=display_name.encode("utf-8"))
    
    return RNS.prettyhexrep(identity.hash)

def send_lxm(dest_hex, text, img_b64=None):
    try:
        dest_hash = bytes.fromhex(dest_hex)
        recipient = RNS.Destination(None, RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery")
        recipient.hash = dest_hash
        lxm = LXMF.LXMessage(recipient, lxm_router.identity, text, title="RNS Lite")
        if img_b64:
            lxm.fields["image"] = base64.b64decode(img_b64)
        lxm_router.handle_outbound(lxm)
        return "Message Queued"
    except Exception as e: return str(e)

def get_updates():
    global inbox
    data = {"inbox": list(inbox), "nodes": list(known_nodes.keys())}
    inbox = [] # Clear seen messages
    return data