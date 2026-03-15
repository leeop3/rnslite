import RNS
import LXMF
import threading
import os
import time
import struct
from RNS.Interfaces.Interface import Interface
from collections import deque
from bt_wrapper import BtWrapper
import rnode_config as _rc

# KISS Constants for RNode Hardware
FEND, FESC, TFEND, TFESC = 0xC0, 0xDB, 0xDC, 0xDD
CMD_DATA, CMD_FREQUENCY, CMD_BANDWIDTH, CMD_TXPOWER, CMD_SF, CMD_CR, CMD_RADIO_STATE, CMD_DETECT, CMD_READY = 0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x08, 0x0F

destination = None
lxmf_router = None
_data_lock = threading.Lock()
chat_messages = deque(maxlen=500)
seen_announces = []

def kiss_cmd(cmd, data=b""):
    out = [FEND, cmd]
    for b in data:
        if b == FEND: out += [FESC, TFEND]
        elif b == FESC: out += [FESC, TFESC]
        else: out.append(b)
    out.append(FEND)
    return bytes(out)

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
        # Announce/Mesh Management deques
        self.oa_freq_deque = deque(maxlen=16)
        self.ia_freq_deque = deque(maxlen=16)
        self.announces_held = []
        self.held_announces = {}
        self.ic_new_time = self.ic_rate_count = self.ic_burst_freq = 0
        self.ic_burst_limit, self.ic_burst_active, self.ic_burst_start = 5, False, 0
        self._kiss_buf, self._in_frame, self._escape = [], False, False
        threading.Thread(target=self._read_loop, daemon=True).start()

    def _read_loop(self):
        while self.online:
            try:
                data = self.bt.read(512)
                if data:
                    self.rxb += len(data)
                    for byte in data:
                        if byte == FEND:
                            if self._in_frame and len(self._kiss_buf) > 1:
                                if self._kiss_buf[0] == CMD_DATA:
                                    self.owner.inbound(bytes(self._kiss_buf[1:]), self)
                            self._kiss_buf, self._in_frame, self._escape = [], True, False
                        elif self._in_frame:
                            if byte == FESC: self._escape = True
                            elif self._escape:
                                self._escape = False
                                if byte == TFEND: self._kiss_buf.append(FEND)
                                elif byte == TFESC: self._kiss_buf.append(FESC)
                            else: self._kiss_buf.append(byte)
                else: time.sleep(0.01)
            except: self.online = False

    def process_outgoing(self, data):
        self.txb += len(data)
        self.bt.write(kiss_cmd(CMD_DATA, data))

def message_received(message):
    sender = RNS.prettyhexrep(message.source_hash).strip("<>")
    text = message.content.decode("utf-8") if isinstance(message.content, bytes) else message.content
    with _data_lock: chat_messages.append({"sender": sender, "content": text})

def announce_handler(aspect_filter, data, packet):
    hash_str = RNS.prettyhexrep(packet.destination_hash).strip("<>")
    name = data.decode("utf-8", "ignore") if data else "Unknown"
    with _data_lock:
        for a in seen_announces:
            if a["hash"] == hash_str:
                a["name"] = name
                return
        seen_announces.append({"hash": hash_str, "name": name})

def start(kt_service, display_name="LiteNode"):
    global destination, lxmf_router
    storage = "/data/data/com.leeop3.rnslite/files"
    
    # 1. Initialize Wrapper
    wrapper = BtWrapper(kt_service)
    
    # 2. Wake up Radio (Sideband Standard)
    cfg = _rc.get()
    wrapper.write(kiss_cmd(CMD_DETECT, bytes([0x00])))
    time.sleep(0.2)
    wrapper.write(kiss_cmd(CMD_RADIO_STATE, bytes([0x00])))
    time.sleep(0.5)
    wrapper.write(kiss_cmd(CMD_FREQUENCY, struct.pack(">I", cfg["frequency"])))
    wrapper.write(kiss_cmd(CMD_BANDWIDTH, struct.pack(">I", cfg["bandwidth"])))
    wrapper.write(kiss_cmd(CMD_TXPOWER, bytes([cfg["txpower"]])))
    wrapper.write(kiss_cmd(CMD_SF, bytes([cfg["sf"]])))
    wrapper.write(kiss_cmd(CMD_CR, bytes([cfg["cr"]])))
    wrapper.write(kiss_cmd(CMD_RADIO_STATE, bytes([0x01])))
    time.sleep(1.0)
    wrapper.write(kiss_cmd(CMD_READY, bytes([0x00])))

    # 3. Start RNS
    os.makedirs(storage + "/.reticulum", exist_ok=True)
    with open(storage + "/.reticulum/config", "w") as f:
        f.write("[reticulum]\nenable_auto_interface = No\n")
    
    r = RNS.Reticulum.get_instance() or RNS.Reticulum(configdir=storage + "/.reticulum")
    RNS.Transport.register_announce_handler(announce_handler)
    
    # 4. Attach Interface
    iface = AndroidBTInterface(RNS.Transport, "RNodeBT", wrapper)
    RNS.Transport.interfaces.append(iface)
    
    # 5. Setup Identity & LXMF
    id_path = os.path.join(storage, "identity")
    identity = RNS.Identity.from_file(id_path) if os.path.exists(id_path) else RNS.Identity()
    if not os.path.exists(id_path): identity.to_file(id_path)
    
    lxmf_router = LXMF.LXMRouter(storagepath=storage + "/lxmf", autopeer=True)
    lxmf_router.register_delivery_callback(message_received)
    destination = lxmf_router.register_delivery_identity(identity, display_name=display_name)
    
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
        res = {"inbox": list(chat_messages), "nodes": [a["name"] + " (" + a["hash"] + ")" for a in seen_announces]}
        chat_messages.clear()
        return res