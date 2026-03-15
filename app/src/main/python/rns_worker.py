import RNS
import LXMF
import os, threading, time, socket, base64
from collections import deque

# Patch socket for Android
if not hasattr(socket, "if_nametoindex"):
    socket.if_nametoindex = lambda name: 0

FEND, FESC, TFEND, TFESC = 0xC0, 0xDB, 0xDC, 0xDD

class BTInterface(RNS.Interfaces.Interface.Interface):
    def __init__(self, owner, name, kt_service):
        self.owner, self.name, self.kt = owner, name, kt_service
        self.online = self.IN = self.OUT = self.ingress_control = True
        self.HW_MTU, self.forwarded_count, self.bitrate, self.rxb, self.txb = 1064, 0, 0, 0, 0
        self.mode = RNS.Interfaces.Interface.Interface.MODE_FULL
        self.created = time.time()
        self.parent_interface = None
        self.is_connected = True
        self.oa_freq_deque = deque(maxlen=10)
        self.ia_freq_deque = deque(maxlen=10)
        self.announces_held = []
        self.held_announces = []
        self.announce_cap = 20
        self.ic_new_time = self.ic_rate_count = self.ic_burst_freq = 0
        self.ic_burst_limit = 5
        self.ic_burst_active = False
        self.ic_burst_start = 0
        threading.Thread(target=self.read_loop, daemon=True).start()
        RNS.log("BTInterface synchronized.")

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
    content = lxm.content.decode("utf-8") if isinstance(lxm.content, bytes) else lxm.content
    inbox.append({"sender": sender, "content": content, "time": time.strftime("%H:%M")})
    RNS.log(f"LXMF Message from {sender}")

def announce_handler(aspect_filter, data, packet):
    node_hash = RNS.prettyhexrep(packet.destination_hash)
    try:
        name = data.decode("utf-8")
        known_nodes[node_hash] = name
        RNS.log(f"Heard announce from {name}")
    except:
        known_nodes[node_hash] = "Unknown"

def start(storage_path, kt_service, display_name):
    global lxm_router
    r = RNS.Reticulum.get_instance()
    if r is None:
        if not os.path.exists(storage_path): os.makedirs(storage_path)
        config_path = os.path.join(storage_path, "config")
        with open(config_path, "w") as f:
            f.write("[reticulum]\nenable_auto_interface = No\n")
        r = RNS.Reticulum(configdir=storage_path)
        RNS.Transport.register_announce_handler(announce_handler)

    RNS.Transport.interfaces = [i for i in RNS.Transport.interfaces if i.name != "RNode_BT"]
    bt_if = BTInterface(r, "RNode_BT", kt_service)
    RNS.Transport.interfaces.append(bt_if)
    
    id_dir = os.path.join(storage_path, "storage")
    if not os.path.exists(id_dir): os.makedirs(id_dir)
    id_path = os.path.join(id_dir, "identity")
    identity = RNS.Identity.from_file(id_path) if os.path.exists(id_path) else RNS.Identity()
    if not os.path.exists(id_path): identity.to_file(id_path)
    
    if lxm_router is None:
        lxm_router = LXMF.LXMRouter(identity=identity, storagepath=storage_path)
        lxm_router.register_delivery_callback(message_received)
    
    # Send Announce
    announce_dest = RNS.Destination(identity, RNS.Destination.IN, RNS.Destination.SINGLE, "lxmf", "delivery")
    announce_dest.announce(app_data=display_name.encode("utf-8"))
    RNS.log("System Online. Address: " + RNS.prettyhexrep(identity.hash))
    return RNS.prettyhexrep(identity.hash)

def send_text(dest_hex, text):
    try:
        dest_hash = bytes.fromhex(dest_hex)
        # RECALL logic
        recp_id = RNS.Identity.recall(dest_hash)
        
        # In Sideband, if we dont know the peer, we request a path 
        # but we CANT send an LXMF until we hear their announce.
        if recp_id is None:
            RNS.log(f"Identity for {dest_hex} unknown. Requesting path...")
            RNS.Transport.request_path(dest_hash)
            return "Unknown Peer. Path requested. Try again in 30s."
            
        recipient = RNS.Destination(recp_id, RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery")
        lxm = LXMF.LXMessage(recipient, lxm_router.identity, text, title="RNS Lite")
        lxm_router.handle_outbound(lxm)
        return "Message Queued"
    except Exception as e:
        RNS.log(f"Send Failed: {e}")
        return str(e)

def get_updates():
    global inbox
    nodes = [v + " (" + k + ")" for k, v in known_nodes.items()]
    data = {"inbox": list(inbox), "nodes": nodes, "logs": []} # Added empty logs key for bridge compatibility
    inbox = []
    return data