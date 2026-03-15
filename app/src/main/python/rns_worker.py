import RNS
import LXMF
import threading
import os
import time
import struct
from RNS.Interfaces.Interface import Interface
from collections import deque
import rnode_config as _rc
from bt_wrapper import BtWrapper

# KISS Constants
KISS_FEND, KISS_FESC, KISS_TFEND, KISS_TFESC = 0xC0, 0xDB, 0xDC, 0xDD
CMD_DATA        = 0x00
CMD_FREQUENCY   = 0x01
CMD_BANDWIDTH   = 0x02
CMD_TXPOWER     = 0x03
CMD_SF          = 0x04
CMD_CR          = 0x05
CMD_RADIO_STATE = 0x06
CMD_STAT_RX     = 0x07
CMD_DETECT      = 0x08
CMD_READY       = 0x0F

destination = None
lxmf_router = None
_data_lock = threading.Lock()
chat_messages = deque(maxlen=500)
seen_announces = []

def kiss_escape(data):
    out = []
    for b in data:
        if b == KISS_FEND: out += [KISS_FESC, KISS_TFEND]
        elif b == KISS_FESC: out += [KISS_FESC, KISS_TFESC]
        else: out.append(b)
    return bytes(out)

def kiss_cmd(cmd, data=b""):
    return bytes([KISS_FEND, cmd]) + kiss_escape(data) + bytes([KISS_FEND])

def configure_rnode(wrapper):
    cfg = _rc.get()
    RNS.log("Initialising RNode hardware...")
    # Reset KISS state
    wrapper.write(bytes([KISS_FEND, KISS_FEND, KISS_FEND]))
    time.sleep(0.5)
    # Detect RNode
    wrapper.write(kiss_cmd(CMD_DETECT, bytes([0x00])))
    time.sleep(0.5)
    # Configure Radio Parameters
    wrapper.write(kiss_cmd(CMD_FREQUENCY, struct.pack(">I", cfg["frequency"])))
    time.sleep(0.2)
    wrapper.write(kiss_cmd(CMD_BANDWIDTH, struct.pack(">I", cfg["bandwidth"])))
    time.sleep(0.2)
    wrapper.write(kiss_cmd(CMD_TXPOWER, bytes([cfg["txpower"]])))
    time.sleep(0.2)
    wrapper.write(kiss_cmd(CMD_SF, bytes([cfg["sf"]])))
    time.sleep(0.2)
    wrapper.write(kiss_cmd(CMD_CR, bytes([cfg["cr"]])))
    time.sleep(0.2)
    # Set Radio to ON (RX Mode)
    wrapper.write(kiss_cmd(CMD_RADIO_STATE, bytes([0x01])))
    time.sleep(1.0)
    # Final Ready Signal
    wrapper.write(kiss_cmd(CMD_READY, bytes([0x01])))
    RNS.log("RNode hardware online and listening.")

class AndroidBTInterface(Interface):
    def __init__(self, owner, name, wrapper):
        super().__init__()
        self.owner, self.name, self.bt = owner, name, wrapper
        self.online = self.IN = self.OUT = self.ingress_control = True
        self.mode = Interface.MODE_FULL
        self.rxb = self.txb = 0
        self.created = time.time()
        self.parent_interface = None
        self.is_connected = True
        # Mandatory deques for RNS
        self.oa_freq_deque = deque(maxlen=16)
        self.ia_freq_deque = deque(maxlen=16)
        self.announces_held = []
        self.held_announces = {}
        self.ic_new_time = 0
        self.ic_max_rate = 8
        self.ic_rate_count = 0
        self.ic_burst_freq = 0
        self.ic_burst_limit = 5
        self.ic_burst_active = False
        self.ic_burst_start = 0
        self._kiss_buf, self._in_frame, self._escape = [], False, False
        threading.Thread(target=self._read_loop, daemon=True).start()

    def _read_loop(self):
        while self.online:
            try:
                data = self.bt.read(1024)
                if data: self._parse_kiss(data)
                else: time.sleep(0.02)
            except: self.online = False

    def _parse_kiss(self, data):
        for byte in data:
            if byte == KISS_FEND:
                if self._in_frame and len(self._kiss_buf) > 1:
                    port = self._kiss_buf[0]
                    if port == CMD_DATA:
                        self.owner.inbound(bytes(self._kiss_buf[1:]), self)
                self._kiss_buf, self._in_frame, self._escape = [], True, False
            elif self._in_frame:
                if byte == KISS_FESC: self._escape = True
                elif self._escape:
                    self._escape = False
                    if byte == KISS_TFEND: self._kiss_buf.append(KISS_FEND)
                    elif byte == KISS_TFESC: self._kiss_buf.append(KISS_FESC)
                else: self._kiss_buf.append(byte)

    def process_outgoing(self, data):
        self.txb += len(data)
        self.bt.write(kiss_cmd(CMD_DATA, data))

def message_received(message):
    sender = RNS.prettyhexrep(message.source_hash).strip("<>")
    text = message.content.decode("utf-8") if isinstance(message.content, bytes) else message.content
    with _data_lock: chat_messages.append({"sender": sender, "content": text})

def announce_handler(destination_hash, announced_identity, app_data):
    hash_str = RNS.prettyhexrep(destination_hash).strip("<>")
    try:
        # Decode msgpack-style name if possible (Sideband compatible)
        name = app_data.decode("utf-8", "ignore") if app_data else "Unknown"
    except: name = "Unknown"
    
    with _data_lock:
        for a in seen_announces:
            if a["hash"] == hash_str:
                a["name"] = name
                return
        seen_announces.append({"hash": hash_str, "name": name})

def start(bt_socket, display_name="LiteNode"):
    global destination, lxmf_router
    storage = "/data/data/com.leeop3.rnslite/files"
    
    # Pre-configure RNS config to match Sideband
    os.makedirs(storage + "/.reticulum", exist_ok=True)
    with open(storage + "/.reticulum/config", "w") as f:
        f.write("[reticulum]\nenable_auto_interface = No\nshare_instance = Yes\n")
    
    # Init RNS
    r = RNS.Reticulum(configdir=storage + "/.reticulum")
    
    # Setup BT Wrapper and Radio Handshake
    wrapper = BtWrapper(bt_socket)
    configure_rnode(wrapper)
    
    # Interface Registration
    iface = AndroidBTInterface(RNS.Transport, "RNodeBT", wrapper)
    RNS.Transport.interfaces.append(iface)
    
    # Identity
    id_path = os.path.join(storage, "identity")
    identity = RNS.Identity.from_file(id_path) if os.path.exists(id_path) else RNS.Identity()
    if not os.path.exists(id_path): identity.to_file(id_path)
    
    # LXMF
    lxmf_router = LXMF.LXMRouter(storagepath=storage + "/lxmf", autopeer=True)
    lxmf_router.register_delivery_callback(message_received)
    destination = lxmf_router.register_delivery_identity(identity, display_name=display_name)
    
    # Important: Register for LXMF announces specifically
    RNS.Transport.register_announce_handler(announce_handler)
    
    # Final Announce
    destination.announce()
    return RNS.prettyhexrep(identity.hash).strip("<>")

def send_text(dest_hex, text):
    try:
        dest_hash = bytes.fromhex(dest_hex.strip("<>"))
        recp_id = RNS.Identity.recall(dest_hash)
        if not recp_id: 
            RNS.Transport.request_path(dest_hash)
            return "Peer unknown - Path Requested"
        lxmf_dest = RNS.Destination(recp_id, RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery")
        msg = LXMF.LXMessage(lxmf_dest, destination, text)
        lxmf_router.handle_outbound(msg)
        return "Message Queued"
    except Exception as e: return str(e)

def get_updates():
    with _data_lock:
        res = {"inbox": list(chat_messages), "nodes": [a["name"] + " (" + a["hash"] + ")" for a in seen_announces]}
        chat_messages.clear()
        return res