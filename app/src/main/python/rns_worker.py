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

destination = None
lxmf_router = None
_data_lock = threading.Lock()
chat_messages = []
seen_announces = {}

def log_hook(msg):
    print(f"DEBUG_RNS: {msg}")

RNS.log = lambda msg, lvl=3: log_hook(msg)

def _noop_signal(sig, handler): pass

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
    wrapper.write(bytes([KISS_FEND, KISS_FEND, KISS_FEND]))
    time.sleep(0.5)
    wrapper.write(kiss_cmd(CMD_DETECT, bytes([0x00])))
    time.sleep(0.5)
    wrapper.write(kiss_cmd(CMD_FREQUENCY, struct.pack(">I", cfg["frequency"])))
    wrapper.write(kiss_cmd(CMD_RADIO_STATE, bytes([0x01])))
    time.sleep(0.5)
    wrapper.write(kiss_cmd(CMD_READY, bytes([0x01])))

class AndroidBTInterface(RNS.Interfaces.Interface.Interface):
    def __init__(self, owner, name, wrapper):
        self.owner = owner
        self.name = name
        self.bt = wrapper
        self.online = True
        self.IN = self.OUT = self.ingress_control = True
        self.mode = RNS.Interfaces.Interface.Interface.MODE_FULL
        self.bitrate = 1200
        self.rxb = 0 # Fixed: Added missing attribute
        self.txb = 0 # Fixed: Added missing attribute
        self.forwarded_count = 0
        self.created = time.time()
        self.parent_interface = None
        self.is_connected = True
        
        # Announce/Discovery variables
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
                        pkt = bytes(self._kiss_buf[1:])
                        self.rxb += len(pkt)
                        self.owner.inbound(pkt, self)
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
        hash_str = RNS.prettyhexrep(dest_hash).strip("<>")
        name = "Node " + hash_str[:6]
        if app_data:
            try:
                raw = app_data.decode("utf-8", "ignore")
                name = "".join(c for c in raw if c.isprintable()).strip()
            except: pass
        with _data_lock:
            seen_announces[hash_str] = name
        print(f"DEBUG_RNS: Peer Discovery -> {name}")

def message_received(lxm):
    sender = RNS.prettyhexrep(lxm.source_hash).strip("<>")
    content = lxm.content.decode("utf-8", "ignore") if isinstance(lxm.content, bytes) else lxm.content
    with _data_lock:
        chat_messages.append(f"{sender}: {content}")

def start(storage_path, kt_service, display_name):
    global destination, lxmf_router
    signal.signal = signal.SIGINT, _noop_signal
    
    # 1. Critical: Setup internal Reticulum storage path
    rns_dir = os.path.join(storage_path, ".reticulum")
    storage_dir = os.path.join(rns_dir, "storage")
    os.makedirs(os.path.join(storage_dir, "identities"), exist_ok=True)
    
    # 2. Lock Identity (The Persistence Fix)
    master_id_path = os.path.join(storage_path, "master_identity")
    if os.path.exists(master_id_path):
        identity = RNS.Identity.from_file(master_id_path)
    else:
        identity = RNS.Identity()
        identity.to_file(master_id_path)
    
    # Force this identity into Reticulum internal storage so it loads on init
    identity.to_file(os.path.join(storage_dir, "identity"))

    # 3. Startup Config
    if not hasattr(socket, "if_nametoindex"): socket.if_nametoindex = lambda name: 0
    with open(os.path.join(rns_dir, "config"), "w") as f:
        f.write("[reticulum]\nenable_auto_interface = No\nshare_instance = No\n")

    # 4. Start Engine
    r = RNS.Reticulum.get_instance() or RNS.Reticulum(configdir=rns_dir)
    
    # 5. Interface & Handler
    wrapper = BtWrapper(kt_service)
    configure_rnode(wrapper)
    RNS.Transport.interfaces = [i for i in RNS.Transport.interfaces if i.name != "RNodeBT"]
    RNS.Transport.interfaces.append(AndroidBTInterface(RNS.Transport, "RNodeBT", wrapper))
    RNS.Transport.register_announce_handler(SidebandHandler())
    
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
        recipient = RNS.Destination(recp_id, RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery")
        if recp_id is None:
            recipient.hash = dest_hash
            RNS.Transport.request_path(dest_hash)
            return "Discovery requested..."
        lxm = LXMF.LXMessage(recipient, destination, text)
        lxmf_router.handle_outbound(lxm)
        return "Sent"
    except Exception as e: return str(e)

def get_updates():
    with _data_lock:
        m = list(chat_messages)
        n = [f"{name} ({h})" for h, name in seen_announces.items()]
        chat_messages.clear()
        return {"inbox": m, "nodes": n}