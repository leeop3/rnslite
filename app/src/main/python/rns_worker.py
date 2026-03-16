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
        self.owner, self.name, self.bt = owner, name, wrapper
        self.online = self.IN = self.OUT = self.ingress_control = True
        self.mode = RNS.Interfaces.Interface.Interface.MODE_FULL
        self.bitrate = 1200
        self.rxb = self.txb = self.forwarded_count = 0
        self.created = time.time()
        self.parent_interface = None
        self.is_connected = True
        self.oa_freq_deque = deque(maxlen=16)
        self.ia_freq_deque = deque(maxlen=16)
        self.announces_held = []
        self.held_announces = []
        self.ic_new_time = self.ic_rate_count = self.ic_burst_freq = 0
        self.ic_burst_limit, self.ic_burst_active, self.ic_burst_start = 5, False, 0
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

def _decode_name(data):
    if not data: return "Unknown"
    try:
        # Look for printable strings inside Sideband binary app_data
        import re
        m = re.search(b"[\\x20-\\x7E]{2,}", data)
        return m.group(0).decode("utf-8") if m else "Mesh Node"
    except: return "Mesh Node"

class SidebandHandler:
    aspect_filter = "lxmf.delivery"
    def received_announce(self, dest_hash, identity, app_data):
        h = RNS.prettyhexrep(dest_hash).strip("<>")
        name = _decode_name(app_data)
        with _data_lock: seen_announces[h] = name
        print(f"DEBUG_RNS: Discovery Success - {name}")

def message_received(lxm):
    sender = RNS.prettyhexrep(lxm.source_hash).strip("<>")
    content = lxm.content.decode("utf-8", "ignore") if isinstance(lxm.content, bytes) else lxm.content
    with _data_lock: chat_messages.append(f"{sender}: {content}")

def start(storage_path, kt_service, display_name):
    global destination, lxmf_router
    signal.signal = lambda s, h: None
    # Fix paths to match ADB logs
    base = "/data/user/0/com.leeop3.rnslite/files"
    rns_dir = os.path.join(base, ".reticulum")
    storage_dir = os.path.join(rns_dir, "storage")
    os.makedirs(os.path.join(storage_dir, "identities"), exist_ok=True)
    
    # Pre-configure Identity
    id_path = os.path.join(base, "user_identity")
    identity = RNS.Identity.from_file(id_path) if os.path.exists(id_path) else RNS.Identity()
    if not os.path.exists(id_path): identity.to_file(id_path)
    # FORCE SYNC: Copy to the path Reticulum searches
    identity.to_file(os.path.join(storage_dir, "identity"))

    if not hasattr(socket, "if_nametoindex"): socket.if_nametoindex = lambda n: 0
    with open(os.path.join(rns_dir, "config"), "w") as f:
        f.write("[reticulum]\nenable_auto_interface = No\nshare_instance = No\n")

    r = RNS.Reticulum.get_instance() or RNS.Reticulum(configdir=rns_dir)
    
    wrapper = BtWrapper(kt_service)
    configure_rnode(wrapper)
    RNS.Transport.interfaces = [i for i in RNS.Transport.interfaces if i.name != "RNodeBT"]
    iface = AndroidBTInterface(RNS.Transport, "RNodeBT", wrapper)
    RNS.Transport.interfaces.append(iface)
    RNS.Transport.register_announce_handler(SidebandHandler())
    
    if lxmf_router is None:
        lxmf_router = LXMF.LXMRouter(identity=identity, storagepath=os.path.join(base, "lxmf"), autopeer=True)
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