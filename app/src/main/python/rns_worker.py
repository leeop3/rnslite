import RNS
import LXMF
import threading
import os, time, struct, socket, base64, signal
from collections import deque
import rnode_config as _rc
from bt_wrapper import BtWrapper

# KISS Constants
KISS_FEND, KISS_FESC, KISS_TFEND, KISS_TFESC = 0xC0, 0xDB, 0xDC, 0xDD
CMD_DATA, CMD_FREQUENCY, CMD_RADIO_STATE, CMD_DETECT, CMD_READY = 0x00, 0x01, 0x06, 0x08, 0x0F

reticulum_instance = None
destination = None
lxmf_router = None
_data_lock = threading.Lock()
chat_messages = deque(maxlen=100) 
seen_announces = {}

RNS.log = lambda msg, lvl=3: print(f"DEBUG_RNS: {msg}")

def kiss_cmd(cmd, data=b""):
    out = [KISS_FEND, cmd]
    for b in data:
        if b == KISS_FEND: out += [KISS_FESC, KISS_TFEND]
        elif b == KISS_FESC: out += [KISS_FESC, KISS_TFESC]
        else: out.append(b)
    out.append(KISS_FEND)
    return bytes(out)

def configure_rnode(wrapper):
    cfg = _rc.get()
    try:
        wrapper.write(bytes([KISS_FEND, KISS_FEND, KISS_FEND]))
        time.sleep(0.5)
        wrapper.write(kiss_cmd(CMD_DETECT, bytes([0x00])))
        time.sleep(0.5)
        wrapper.write(kiss_cmd(CMD_FREQUENCY, struct.pack(">I", cfg["frequency"])))
        wrapper.write(kiss_cmd(CMD_RADIO_STATE, bytes([0x01])))
        time.sleep(0.5)
        wrapper.write(kiss_cmd(CMD_READY, bytes([0x01])))
    except Exception as e: print(f"DEBUG_BT: Config error: {e}")

class AndroidBTInterface(RNS.Interfaces.Interface.Interface):
    def __init__(self, owner, name, wrapper):
        self.owner, self.name, self.bt = owner, name, wrapper
        self.online = self.IN = self.OUT = self.ingress_control = True
        self.mode = RNS.Interfaces.Interface.Interface.MODE_FULL
        self.rxb = self.txb = self.forwarded_count = 0
        self.bitrate = 1200
        self.created = time.time()
        self.parent_interface = None
        self.is_connected = True
        self.oa_freq_deque = deque(maxlen=16)
        self.ia_freq_deque = deque(maxlen=16)
        self.announces_held = []
        self.held_announces = []
        self.announce_cap = 20
        self.ic_new_time = 0
        self.ic_max_rate = 8
        self.ic_rate_count = 0
        self.ic_burst_freq = 0
        self.ic_burst_limit = 5
        self.ic_burst_active = False
        self.ic_burst_start = 0
        self._kiss_buf, self._in_frame, self._escape = [], False, False
        threading.Thread(target=self._read_loop, daemon=True).start()

    def process_outgoing(self, data):
        self.txb += len(data)
        self.bt.write(kiss_cmd(CMD_DATA, data))

    def _read_loop(self):
        while self.online:
            try:
                data = self.bt.read(1024)
                if data: self._parse_kiss(data)
                else: time.sleep(0.01)
            except: self.online = False

    def _parse_kiss(self, data):
        for byte in data:
            if byte == KISS_FEND:
                if self._in_frame and len(self._kiss_buf) > 1:
                    if self._kiss_buf[0] == CMD_DATA:
                        self.owner.inbound(bytes(self._kiss_buf[1:]), self)
                self._kiss_buf, self._in_frame, self._escape = [], True, False
            elif self._in_frame:
                if byte == KISS_FESC: self._escape = True
                elif self._escape:
                    self._escape = False
                    if byte == KISS_TFEND: self._kiss_buf.append(KISS_FEND)
                    elif byte == KISS_TFESC: self._kiss_buf.append(KISS_FESC)
                else: self._kiss_buf.append(byte)

class SidebandHandler:
    aspect_filter = "lxmf.delivery"
    def received_announce(self, dest_hash, identity, app_data):
        h = RNS.prettyhexrep(dest_hash).strip("<>")
        name = "Mesh Node"
        if app_data:
            try:
                import re
                m = re.search(b"[\\x20-\\x7E]{2,}", app_data)
                if m: name = m.group(0).decode("utf-8")
            except: pass
        with _data_lock: seen_announces[h] = name
        print(f"DEBUG_RNS: Peer Discovered -> {name}")

def message_received(lxm):
    sender = RNS.prettyhexrep(lxm.source_hash).strip("<>")
    content = lxm.content.decode("utf-8", "ignore") if isinstance(lxm.content, bytes) else lxm.content
    with _data_lock: chat_messages.append(f"{sender}: {content}")

def start(storage_path, kt_service, display_name):
    global reticulum_instance, destination, lxmf_router
    signal.signal = lambda s, h: None
    
    # 1. SETUP DIRECTORIES
    rns_dir = os.path.join(storage_path, ".reticulum")
    storage_dir = os.path.join(rns_dir, "storage")
    os.makedirs(storage_dir, exist_ok=True)
    os.makedirs(os.path.join(storage_dir, "identities"), exist_ok=True)
    
    # 2. THE NUCLEAR PERSISTENCE FIX
    # We load the ID and then manually write it to the EXACT path RNS expects
    master_backup = os.path.join(storage_path, "master_id_v2")
    rns_id_file = os.path.join(storage_dir, "identity")
    
    if os.path.exists(master_backup):
        identity = RNS.Identity.from_file(master_backup)
    else:
        identity = RNS.Identity()
        identity.to_file(master_backup)
    
    # Force write to RNS storage slot and flush to disk
    with open(rns_id_file, "wb") as f:
        f.write(identity.get_private_key())
        f.flush()
        os.fsync(f.fileno()) # Physically force write to storage chip

    # 3. CONFIG
    if not hasattr(socket, "if_nametoindex"): socket.if_nametoindex = lambda n: 0
    with open(os.path.join(rns_dir, "config"), "w") as f:
        f.write("[reticulum]\nenable_auto_interface = No\nshare_instance = No\n")

    # 4. START ENGINE (It will now see the identity file)
    if reticulum_instance is None:
        reticulum_instance = RNS.Reticulum(configdir=rns_dir)
        RNS.Transport.register_announce_handler(SidebandHandler())
    
    # 5. HARDWARE & INTERFACE
    wrapper = BtWrapper(kt_service)
    iface = AndroidBTInterface(RNS.Transport, "RNodeBT", wrapper)
    RNS.Transport.interfaces = [i for i in RNS.Transport.interfaces if i.name != "RNodeBT"]
    RNS.Transport.interfaces.append(iface)
    configure_rnode(wrapper)
    
    # 6. LXMF
    if lxmf_router is None:
        lxmf_router = LXMF.LXMRouter(identity=identity, storagepath=os.path.join(storage_path, "lxmf"), autopeer=True)
        lxmf_router.register_delivery_callback(message_received)
    
    destination = lxmf_router.register_delivery_identity(identity, display_name=display_name)
    destination.announce()
    
    return RNS.prettyhexrep(destination.hash).strip("<>")

def send_text(dest_hex, text):
    try:
        dest_hash = bytes.fromhex(dest_hex.strip("<>"))
        recp_id = RNS.Identity.recall(dest_hash)
        if recp_id is None:
            RNS.Transport.request_path(dest_hash)
            return "Discovery requested..."
        recipient = RNS.Destination(recp_id, RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery")
        lxm = LXMF.LXMessage(recipient, destination, text)
        lxmf_router.handle_outbound(lxm)
        return "Sent"
    except Exception as e: return str(e)

def get_updates():
    with _data_lock:
        m, n = list(chat_messages), [f"{name} ({h})" for h, name in seen_announces.items()]
        chat_messages.clear()
        return {"inbox": m, "nodes": n}