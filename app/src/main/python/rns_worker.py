import RNS
import LXMF
import threading
import os, time, struct, socket, base64
from collections import deque
import rnode_config as _rc
from bt_wrapper import BtWrapper

KISS_FEND, KISS_FESC, KISS_TFEND, KISS_TFESC = 0xC0, 0xDB, 0xDC, 0xDD
CMD_DATA, CMD_FREQUENCY, CMD_RADIO_STATE, CMD_DETECT, CMD_READY = 0x00, 0x01, 0x06, 0x08, 0x0F

destination = None
lxmf_router = None
_data_lock = threading.Lock()
chat_messages = deque(maxlen=500)
seen_announces = []
log_buffer = []

def log_hook(msg):
    print(f"DEBUG_RNS: {msg}")
    log_buffer.append(str(msg))
    if len(log_buffer) > 50: log_buffer.pop(0)

RNS.log = lambda msg, lvl=3: log_hook(msg)

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
    wrapper.write(kiss_cmd(CMD_DETECT, bytes([0x00])))
    time.sleep(0.5)
    wrapper.write(kiss_cmd(CMD_FREQUENCY, struct.pack(">I", cfg["frequency"])))
    wrapper.write(kiss_cmd(CMD_RADIO_STATE, bytes([0x01])))
    time.sleep(0.5)
    wrapper.write(kiss_cmd(CMD_READY, bytes([0x01])))

class AndroidBTInterface(RNS.Interfaces.Interface.Interface):
    def __init__(self, owner, name, wrapper):
        self.owner, self.name, self.bt = owner, name, wrapper
        self.online = self.IN = self.OUT = self.ingress_control = True
        self.mode = Interface.MODE_FULL
        self.rxb = self.txb = 0
        self.HW_MTU = 1064
        self.created = time.time()
        self.parent_interface = None
        self.is_connected = True
        self.oa_freq_deque = deque(maxlen=16)
        self.ia_freq_deque = deque(maxlen=16)
        self.announces_held = []
        self.held_announces = []
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
        print(f"DEBUG_TX: Sending {len(data)} bytes")
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
                        print(f"DEBUG_RX: Received {len(pkt)} bytes")
                        self.owner.inbound(pkt, self)
                self._kiss_buf, self._in_frame, self._escape = [], True, False
            elif self._in_frame:
                if byte == KISS_FESC: self._escape = True
                elif self._escape:
                    self._escape = False
                    if byte == KISS_TFEND: self._kiss_buf.append(KISS_FEND)
                    elif byte == KISS_TFESC: self._kiss_buf.append(KISS_FESC)
                else: self._kiss_buf.append(byte)

def _decode_name(app_data):
    if not app_data: return "Unknown"
    try:
        # Simple extraction for Sideband names
        res = app_data.decode("utf-8", "ignore")
        return "".join(c for c in res if c.isprintable())
    except: return "Mesh Node"

class SidebandAnnounceHandler:
    aspect_filter = "lxmf.delivery"
    def received_announce(self, destination_hash, announced_identity, app_data):
        hash_str = RNS.prettyhexrep(destination_hash).strip("<>")
        name = _decode_name(app_data)
        # Reticulum automatically saves the announced_identity to its internal store
        with _data_lock:
            for a in seen_announces:
                if a["hash"] == hash_str:
                    a["name"] = name
                    return
            seen_announces.append({"hash": hash_str, "name": name})

def message_received(lxm):
    sender = RNS.prettyhexrep(lxm.source_hash).strip("<>")
    content = lxm.content.decode("utf-8") if isinstance(lxm.content, bytes) else lxm.content
    with _data_lock: chat_messages.append({"sender": sender, "content": content})

def start(storage_path, kt_service, display_name):
    global destination, lxmf_router
    storage = "/data/data/com.leeop3.rnslite/files"
    if not hasattr(socket, "if_nametoindex"): socket.if_nametoindex = lambda name: 0
    
    # 1. Setup RNS Directories
    os.makedirs(storage + "/.reticulum", exist_ok=True)
    os.makedirs(storage + "/.reticulum/storage/identities", exist_ok=True)
    with open(storage + "/.reticulum/config", "w") as f:
        f.write("[reticulum]\nenable_auto_interface = No\n")
    
    # 2. Start RNS
    r = RNS.Reticulum.get_instance() or RNS.Reticulum(configdir=storage + "/.reticulum")
    
    # 3. Configure Hardware
    wrapper = BtWrapper(kt_service)
    configure_rnode(wrapper)
    
    # 4. Attach Interface
    RNS.Transport.interfaces = [i for i in RNS.Transport.interfaces if i.name != "RNodeBT"]
    iface = AndroidBTInterface(RNS.Transport, "RNodeBT", wrapper)
    RNS.Transport.interfaces.append(iface)
    
    # 5. Persistent Identity (CRITICAL FIX)
    id_path = os.path.join(storage, "user_identity")
    if os.path.exists(id_path):
        identity = RNS.Identity.from_file(id_path)
        print(f"DEBUG_RNS: Loaded existing identity <{RNS.prettyhexrep(identity.hash)}>")
    else:
        identity = RNS.Identity()
        identity.to_file(id_path)
        print(f"DEBUG_RNS: Created new permanent identity")

    # 6. LXMF & Discovery
    RNS.Transport.register_announce_handler(SidebandAnnounceHandler())
    lxmf_router = LXMF.LXMRouter(identity=identity, storagepath=storage + "/lxmf", autopeer=True)
    lxmf_router.register_delivery_callback(message_received)
    destination = lxmf_router.register_delivery_identity(identity, display_name=display_name)
    
    # 7. Announce
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
            return "Peer unknown. Path requested."
        
        lxm = LXMF.LXMessage(recipient, lxmf_router.identity, text)
        lxmf_router.handle_outbound(lxm)
        return "Queued"
    except Exception as e: return str(e)

def get_updates():
    with _data_lock:
        res = {"inbox": list(chat_messages), "nodes": [f"{a['name']} ({a['hash']})" for a in seen_announces], "logs": list(log_buffer)}
        chat_messages.clear(); log_buffer.clear()
        return res