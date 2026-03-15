import RNS
import LXMF
import threading
import os
import time
import struct
from RNS.Interfaces.Interface import Interface
from collections import deque
import rnode_config as _rc

# KISS Constants
KISS_FEND, KISS_FESC, KISS_TFEND, KISS_TFESC = 0xC0, 0xDB, 0xDC, 0xDD
CMD_DATA, CMD_FREQUENCY, CMD_BANDWIDTH, CMD_TXPOWER, CMD_SF, CMD_CR, CMD_RADIO_STATE, CMD_DETECT, CMD_READY = 0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x08, 0x0F

# Global instances
destination = None
lxmf_router = None
_data_lock = threading.Lock()
chat_messages = deque(maxlen=500)
seen_announces = [] # List of {"hash": str, "name": str}

def kiss_escape(data):
    out = []
    for b in data:
        if b == KISS_FEND: out += [KISS_FESC, KISS_TFEND]
        elif b == KISS_FESC: out += [KISS_FESC, KISS_TFESC]
        else: out.append(b)
    return bytes(out)

def kiss_cmd(cmd, data=b""):
    return bytes([KISS_FEND, cmd]) + kiss_escape(data) + bytes([KISS_FEND])

def configure_rnode(socket):
    cfg = _rc.get()
    RNS.log(f"Configuring RNode hardware...")
    socket.write(kiss_cmd(CMD_DETECT, bytes([0x00])))
    time.sleep(0.3)
    socket.write(kiss_cmd(CMD_RADIO_STATE, bytes([0x00]))) # Radio OFF
    time.sleep(0.5)
    socket.write(kiss_cmd(CMD_FREQUENCY, struct.pack(">I", cfg["frequency"])))
    socket.write(kiss_cmd(CMD_BANDWIDTH, struct.pack(">I", cfg["bandwidth"])))
    socket.write(kiss_cmd(CMD_TXPOWER, bytes([cfg["txpower"]])))
    socket.write(kiss_cmd(CMD_SF, bytes([cfg["sf"]])))
    socket.write(kiss_cmd(CMD_CR, bytes([cfg["cr"]])))
    socket.write(kiss_cmd(CMD_RADIO_STATE, bytes([0x01]))) # Radio ON (Now Listening)
    time.sleep(1.0)
    socket.write(kiss_cmd(CMD_READY, bytes([0x00])))
    RNS.log("RNode hardware online and listening.")

class AndroidBTInterface(Interface):
    def __init__(self, owner, name, socket):
        super().__init__()
        self.owner, self.name, self._socket = owner, name, socket
        self.rxb = self.txb = 0
        self.online = self.IN = self.OUT = self.ingress_control = True
        self.mode = Interface.MODE_FULL
        self.created = time.time()
        self.parent_interface = None
        self.is_connected = True
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
                data = self._socket.read(1024)
                if data: self._parse_kiss(data)
            except: 
                self.online = False

    def _parse_kiss(self, data):
        for byte in data:
            if byte == KISS_FEND:
                if self._in_frame and len(self._kiss_buf) > 1:
                    if self._kiss_buf[0] == CMD_DATA: 
                        # This is where the app "hears" the other phone
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
        self._socket.write(kiss_cmd(CMD_DATA, data))

def message_received(message):
    sender = RNS.prettyhexrep(message.source_hash).strip("<>")
    text = message.content.decode("utf-8") if isinstance(message.content, bytes) else message.content
    with _data_lock:
        chat_messages.append({"sender": sender, "content": text})

def announce_handler(destination_hash, announced_identity, app_data):
    # This is called when another phone is detected
    hash_str = RNS.prettyhexrep(destination_hash).strip("<>")
    try:
        name = app_data.decode("utf-8", "ignore") if app_data else "Unknown"
    except:
        name = "Unknown"
    
    with _data_lock:
        # Update if exists, otherwise add
        for a in seen_announces:
            if a["hash"] == hash_str:
                a["name"] = name
                return
        seen_announces.append({"hash": hash_str, "name": name})
        RNS.log(f"Detected nearby node: {name} ({hash_str})")

def start(bt_socket, display_name="LiteNode"):
    global destination, lxmf_router
    storage = "/data/data/com.leeop3.rnslite/files"
    
    # 1. PRE-START CONFIG (Ensures RNS behaves on Android)
    os.makedirs(storage + "/.reticulum", exist_ok=True)
    config_content = "[reticulum]\nenable_auto_interface = No\nloglevel = 4\n"
    with open(storage + "/.reticulum/config", "w") as f:
        f.write(config_content)
    
    # 2. START RETICULUM
    r = RNS.Reticulum.get_instance()
    if r is None:
        r = RNS.Reticulum(configdir=storage + "/.reticulum")
    
    # 3. CONFIGURE HARDWARE (Wake up the radio)
    configure_rnode(bt_socket)

    # 4. ATTACH INTERFACE
    RNS.Transport.interfaces = [i for i in RNS.Transport.interfaces if i.name != "RNodeBT"]
    iface = AndroidBTInterface(RNS.Transport, "RNodeBT", bt_socket)
    RNS.Transport.interfaces.append(iface)
    
    # 5. SETUP IDENTITY & LXMF
    id_path = os.path.join(storage, "identity")
    identity = RNS.Identity.from_file(id_path) if os.path.exists(id_path) else RNS.Identity()
    if not os.path.exists(id_path): identity.to_file(id_path)
    
    if lxmf_router is None:
        lxmf_router = LXMF.LXMRouter(storagepath=storage + "/lxmf", autopeer=True)
        lxmf_router.register_delivery_callback(message_received)
    
    # 6. REGISTER LISTENERS
    # We listen for ANY announce to populate the "Nearby" list
    RNS.Transport.register_announce_handler(announce_handler)
    
    destination = lxmf_router.register_delivery_identity(identity, display_name=display_name)
    
    # 7. ANNOUNCE OURSELVES
    destination.announce()
    return RNS.prettyhexrep(destination.hash).strip("<>")

def send_text(dest_hex, text):
    try:
        dest_hash = bytes.fromhex(dest_hex.strip("<>"))
        recp_id = RNS.Identity.recall(dest_hash)
        if not recp_id: 
            RNS.Transport.request_path(dest_hash)
            return "Peer unknown - Requesting Path"
        lxmf_dest = RNS.Destination(recp_id, RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery")
        msg = LXMF.LXMessage(lxmf_dest, destination, text)
        lxmf_router.handle_outbound(msg)
        return "Message Queued"
    except Exception as e: return str(e)

def get_updates():
    with _data_lock:
        res = {
            "inbox": list(chat_messages), 
            "nodes": [f"{a['name']} ({a['hash']})" for a in seen_announces]
        }
        chat_messages.clear()
        return res