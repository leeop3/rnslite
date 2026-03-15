import RNS
import LXMF
import threading
import signal
import os
import time
import struct
from RNS.Interfaces.Interface import Interface
from collections import deque
import rnode_config as _rc
import contacts as _contacts_mod

# KISS Constants
FEND, FESC, TFEND, TFESC = 0xC0, 0xDB, 0xDC, 0xDD
CMD_DATA, CMD_FREQUENCY, CMD_BANDWIDTH, CMD_TXPOWER, CMD_SF, CMD_CR, CMD_RADIO_STATE, CMD_DETECT, CMD_READY = 0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x08, 0x0F

destination = None
lxmf_router = None
_data_lock = threading.Lock()
chat_messages = deque(maxlen=500)
seen_announces = []

def kiss_escape(data):
    out = []
    for b in data:
        if b == FEND: out += [FESC, TFEND]
        elif b == FESC: out += [FESC, TFESC]
        else: out.append(b)
    return bytes(out)

def kiss_cmd(cmd, data=b""):
    return bytes([KISS_FEND, cmd]) + kiss_escape(data) + bytes([KISS_FEND])

def configure_rnode(socket):
    cfg = _rc.get()
    socket.write(kiss_cmd(CMD_DETECT, bytes([0x00])))
    time.sleep(0.3)
    socket.write(kiss_cmd(CMD_RADIO_STATE, bytes([0x00])))
    time.sleep(0.5)
    socket.write(kiss_cmd(CMD_FREQUENCY, struct.pack(">I", cfg["frequency"])))
    socket.write(kiss_cmd(CMD_BANDWIDTH, struct.pack(">I", cfg["bandwidth"])))
    socket.write(kiss_cmd(CMD_TXPOWER, bytes([cfg["txpower"]])))
    socket.write(kiss_cmd(CMD_SF, bytes([cfg["sf"]])))
    socket.write(kiss_cmd(CMD_CR, bytes([cfg["cr"]])))
    socket.write(kiss_cmd(CMD_RADIO_STATE, bytes([0x01])))
    time.sleep(1.0)
    socket.write(kiss_cmd(CMD_READY, bytes([0x00])))

class AndroidBTInterface(Interface):
    def __init__(self, owner, name, socket):
        super().__init__()
        self.owner, self.name, self._socket = owner, name, socket
        self.rxb = self.txb = 0
        self.online = self.IN = self.OUT = self.ingress_control = True
        self.mode = Interface.MODE_FULL
        self.created = time.time()
        self.oa_freq_deque = deque(maxlen=16)
        self.ia_freq_deque = deque(maxlen=16)
        self.announces_held = []
        self.held_announces = []
        self.ic_new_time = self.ic_rate_count = self.ic_burst_freq = 0
        self.ic_burst_limit = 5
        self.ic_burst_active = False
        self.ic_burst_start = 0
        self._kiss_buf, self._in_frame, self._escape = [], False, False
        threading.Thread(target=self._read_loop, daemon=True).start()

    def _read_loop(self):
        while self.online:
            try:
                data = self._socket.read(512)
                if data: self._parse_kiss(data)
            except: self.online = False

    def _parse_kiss(self, data):
        for byte in data:
            if byte == FEND:
                if self._in_frame and len(self._kiss_buf) > 1:
                    if self._kiss_buf[0] == CMD_DATA: self.owner.inbound(bytes(self._kiss_buf[1:]), self)
                self._kiss_buf, self._in_frame, self._escape = [], True, False
            elif self._in_frame:
                if byte == FESC: self._escape = True
                elif self._escape:
                    self._escape = False
                    if byte == KISS_TFEND: self._kiss_buf.append(FEND)
                    elif byte == KISS_TFESC: self._kiss_buf.append(FESC)
                else: self._kiss_buf.append(byte)

    def process_outgoing(self, data):
        self._socket.write(kiss_cmd(CMD_DATA, data))

def message_received(message):
    sender = RNS.prettyhexrep(message.source_hash).strip("<>")
    text = message.content.decode("utf-8") if isinstance(message.content, bytes) else message.content
    with _data_lock: chat_messages.append({"sender": sender, "content": text})

def announce_handler(aspect_filter, data, packet):
    hash_str = RNS.prettyhexrep(packet.destination_hash).strip("<>")
    name = data.decode("utf-8", "ignore") if data else "Unknown"
    with _data_lock: seen_announces.append({"hash": hash_str, "name": name})

def start(bt_socket, display_name="LiteNode"):
    global destination, lxmf_router
    storage = "/data/data/com.leeop3.rnslite/files"
    configure_rnode(bt_socket)
    r = RNS.Reticulum(configdir=storage+"/.reticulum")
    iface = AndroidBTInterface(RNS.Transport, "RNodeBT", bt_socket)
    RNS.Transport.interfaces.append(iface)
    
    id_path = os.path.join(storage, "identity")
    identity = RNS.Identity.from_file(id_path) if os.path.exists(id_path) else RNS.Identity()
    if not os.path.exists(id_path): identity.to_file(id_path)
    
    lxmf_router = LXMF.LXMRouter(storagepath=storage+"/lxmf", autopeer=True)
    destination = lxmf_router.register_delivery_identity(identity, display_name=display_name)
    lxmf_router.register_delivery_callback(message_received)
    RNS.Transport.register_announce_handler(announce_handler)
    
    destination.announce()
    return RNS.prettyhexrep(destination.hash).strip("<>")

def send_text(dest_hex, text):
    try:
        dest_hash = bytes.fromhex(dest_hex.strip("<>"))
        recp_id = RNS.Identity.recall(dest_hash)
        if not recp_id: 
            RNS.Transport.request_path(dest_hash)
            return "Unknown Peer"
        lxmf_dest = RNS.Destination(recp_id, RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery")
        msg = LXMF.LXMessage(lxmf_dest, destination, text)
        lxmf_router.handle_outbound(msg)
        return "Sent"
    except Exception as e: return str(e)

def get_updates():
    with _data_lock:
        res = {"inbox": list(chat_messages), "nodes": [a["name"] + " (" + a["hash"] + ")" for a in seen_announces]}
        chat_messages.clear()
        return res