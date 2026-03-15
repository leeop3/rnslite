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
CMD_DATA, CMD_FREQUENCY, CMD_RADIO_STATE, CMD_DETECT, CMD_READY = 0x00, 0x01, 0x06, 0x08, 0x0F

destination = None
lxmf_router = None
_data_lock = threading.Lock()
chat_messages = deque(maxlen=500)
seen_announces = []

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
    RNS.log("Initialising RNode hardware...")
    wrapper.write(kiss_cmd(CMD_DETECT, bytes([0x00])))
    time.sleep(0.5)
    wrapper.write(kiss_cmd(CMD_RADIO_STATE, bytes([0x00])))
    time.sleep(0.5)
    wrapper.write(kiss_cmd(CMD_FREQUENCY, struct.pack(">I", cfg["frequency"])))
    wrapper.write(kiss_cmd(CMD_RADIO_STATE, bytes([0x01])))
    time.sleep(1.0)
    wrapper.write(kiss_cmd(CMD_READY, bytes([0x01])))
    RNS.log("RNode hardware online and listening.")

class AndroidBTInterface(Interface):
    def __init__(self, owner, name, wrapper):
        super().__init__(owner, name)
        self.bt = wrapper
        self.online = True
        self.IN = self.OUT = self.ingress_control = True
        self.mode = Interface.MODE_FULL
        self.rxb = self.txb = 0
        # Housekeeping
        self.created = time.time()
        self.oa_freq_deque = deque(maxlen=16)
        self.ia_freq_deque = deque(maxlen=16)
        self.announces_held = []
        self.held_announces = []
        self.ic_new_time = self.ic_rate_count = self.ic_burst_freq = 0
        self.ic_burst_limit, self.ic_burst_active, self.ic_burst_start = 5, False, 0
        self._kiss_buf, self._in_frame, self._escape = [], False, False
        threading.Thread(target=self._read_loop, daemon=True).start()

    def _read_loop(self):
        while self.online:
            try:
                data = self.bt.read(1024)
                if data: 
                    self._parse_kiss(data)
                else: 
                    time.sleep(0.01)
            except: self.online = False

    def _parse_kiss(self, data):
        for byte in data:
            if byte == KISS_FEND:
                if self._in_frame and len(self._kiss_buf) > 1:
                    port = self._kiss_buf[0]
                    if port == CMD_DATA:
                        pkt = bytes(self._kiss_buf[1:])
                        self.rxb += len(pkt)
                        # DEBUG LOG: See if the radio is actually hearing packets
                        RNS.log(f"DEBUG: RX Packet on RNodeBT ({len(pkt)} bytes)")
                        self.owner.inbound(pkt, self)
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
        # DEBUG LOG: See if we are trying to send
        RNS.log(f"DEBUG: TX Packet on RNodeBT ({len(data)} bytes)")
        self.bt.write(kiss_cmd(CMD_DATA, data))

def announce_handler(aspect_filter, data, packet):
    hash_str = RNS.prettyhexrep(packet.destination_hash).strip("<>")
    name = data.decode("utf-8", "ignore") if data else "Unknown"
    with _data_lock:
        for a in seen_announces:
            if a["hash"] == hash_str: return
        seen_announces.append({"hash": hash_str, "name": name})
        RNS.log(f"NOTICE: Discovered {name} ({hash_str})")

def start(bt_socket, display_name="LiteNode"):
    global destination, lxmf_router
    storage = "/data/data/com.leeop3.rnslite/files"
    os.makedirs(storage + "/.reticulum", exist_ok=True)
    with open(storage + "/.reticulum/config", "w") as f:
        f.write("[reticulum]\nenable_auto_interface = No\n")
    
    r = RNS.Reticulum(configdir=storage + "/.reticulum")
    wrapper = BtWrapper(bt_socket)
    configure_rnode(wrapper)
    
    iface = AndroidBTInterface(RNS.Transport, "RNodeBT", wrapper)
    RNS.Transport.interfaces.append(iface)
    RNS.Transport.register_announce_handler(announce_handler)
    
    id_path = os.path.join(storage, "identity")
    identity = RNS.Identity.from_file(id_path) if os.path.exists(id_path) else RNS.Identity()
    if not os.path.exists(id_path): identity.to_file(id_path)
    
    lxmf_router = LXMF.LXMRouter(storagepath=storage + "/lxmf", autopeer=True)
    destination = lxmf_router.register_delivery_identity(identity, display_name=display_name)
    
    # Force announce immediately
    destination.announce()
    RNS.log("App is now broadcasting and listening.")
    return RNS.prettyhexrep(destination.hash).strip("<>")

def get_updates():
    with _data_lock:
        res = {"inbox": [], "nodes": [a["name"] + " (" + a["hash"] + ")" for a in seen_announces]}
        return res