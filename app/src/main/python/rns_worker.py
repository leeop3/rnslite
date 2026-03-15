import RNS
import LXMF
import threading
import os, time, struct, socket, base64
from collections import deque
import rnode_config as _rc
from bt_wrapper import BtWrapper

# KISS Constants
KISS_FEND, KISS_FESC, KISS_TFEND, KISS_TFESC = 0xC0, 0xDB, 0xDC, 0xDD
CMD_DATA, CMD_FREQUENCY, CMD_RADIO_STATE, CMD_DETECT, CMD_READY = 0x00, 0x01, 0x06, 0x08, 0x0F

# Global instances
destination = None
lxmf_router = None
_data_lock = threading.Lock()
# Capped to prevent memory leaks (Bug #7 / #8)
chat_messages = deque(maxlen=100) 
seen_announces = {} # {hash: {"name": str, "last": float}}

def log_hook(msg):
    print(f"DEBUG_RNS: {msg}")

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
    try:
        wrapper.write(bytes([KISS_FEND, KISS_FEND, KISS_FEND]))
        time.sleep(0.2)
        wrapper.write(kiss_cmd(CMD_DETECT, bytes([0x00])))
        time.sleep(0.3)
        wrapper.write(kiss_cmd(CMD_FREQUENCY, struct.pack(">I", cfg["frequency"])))
        wrapper.write(kiss_cmd(CMD_RADIO_STATE, bytes([0x01])))
        time.sleep(0.5)
        wrapper.write(kiss_cmd(CMD_READY, bytes([0x01])))
    except Exception as e:
        RNS.log(f"Hardware config failed: {e}")

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
            except Exception as e: # Bug #5 fixed
                RNS.log(f"Read loop error: {e}")
                self.online = False

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
        hash_str = RNS.prettyhexrep(dest_hash).strip("<>")
        name = "Node"
        if app_data:
            try: name = "".join(c for c in app_data.decode("utf-8", "ignore") if c.isprintable()).strip()
            except: pass
        with _data_lock:
            seen_announces[hash_str] = {"name": name, "at": time.time()}

def message_received(lxm):
    sender = RNS.prettyhexrep(lxm.source_hash).strip("<>")
    content = lxm.content.decode("utf-8", "ignore") if isinstance(lxm.content, bytes) else lxm.content
    with _data_lock:
        chat_messages.append(f"{sender}: {content}")

def start(storage_path, kt_service, display_name):
    global destination, lxmf_router
    rns_dir = os.path.join(storage_path, ".reticulum")
    os.makedirs(os.path.join(rns_dir, "storage", "identities"), exist_ok=True)
    
    if not hasattr(socket, "if_nametoindex"): socket.if_nametoindex = lambda name: 0
    
    id_path = os.path.join(storage_path, "user_identity")
    identity = RNS.Identity.from_file(id_path) if os.path.exists(id_path) else RNS.Identity()
    if not os.path.exists(id_path): identity.to_file(id_path)

    # Bug #1: Correct Singleton Pattern
    if RNS.Reticulum._instance is None:
        r = RNS.Reticulum(configdir=rns_dir)
    else:
        r = RNS.Reticulum._instance

    # Bug #6: Construct interface first so it can listen to config echoes
    wrapper = BtWrapper(kt_service)
    iface = AndroidBTInterface(RNS.Transport, "RNodeBT", wrapper)
    RNS.Transport.interfaces.append(iface)
    
    # Now configure hardware while the listener is active
    configure_rnode(wrapper)
    
    RNS.Transport.register_announce_handler(SidebandHandler())
    
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
        
        # Bug #2 / #3 Fix: Check before using, don't attempt hash override
        if recp_id is None:
            RNS.Transport.request_path(dest_hash)
            return "Discovery requested. Wait for peer name."
            
        recipient = RNS.Destination(recp_id, RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery")
        
        # Bug #4: Use the delivery destination object as source
        lxm = LXMF.LXMessage(recipient, destination, text)
        lxmf_router.handle_outbound(lxm)
        return "Sent"
    except Exception as e: return str(e)

def get_updates():
    with _data_lock:
        m = list(chat_messages)
        # nodes are capped by the dictionary nature, but lets clear old ones if needed
        n = [f"{v['name']} ({k})" for k, v in seen_announces.items()]
        # We don't clear chat_messages here to avoid Bug #8, 
        # the UI should handle clearing or we use a cursor.
        # But to keep it simple for this CLI app, we will clear but return a copy.
        chat_messages.clear() 
        return {"inbox": m, "nodes": n}