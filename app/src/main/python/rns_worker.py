import RNS
import LXMF
import os
import threading
import time

# A proxy class to make the Kotlin BT service look like a Serial Port
class BTSerialProxy:
    def __init__(self, kt_service):
        self.kt = kt_service
        self.is_open = True
    def read(self, size=1):
        # We ignore size and just return what the buffer has
        return self.kt.read()
    def write(self, data):
        self.kt.write(data)
    def close(self):
        self.is_open = False
        self.kt.close()
    def flush(self):
        pass

lxm_router = None
received_messages = []

def message_received(lxm):
    sender = RNS.prettyhexrep(lxm.source_hash)
    content = lxm.content.decode("utf-8") if isinstance(lxm.content, bytes) else lxm.content
    received_messages.append({"sender": sender, "content": content})

def start(bt_wrapper_unused, kt_service):
    global lxm_router
    config_dir = RNS.Reticulum.configdir
    
    # 1. Start RNS
    r = RNS.Reticulum(configdir=config_dir)
    
    # 2. Create the Serial Proxy
    serial_port = BTSerialProxy(kt_service)
    
    # 3. Create a RNode Interface (Matches Sideband/RNode hardware)
    # This automatically handles KISS framing and link setup
    from RNS.Interfaces.RNodeInterface import RNodeInterface
    rnode_if = RNodeInterface(
        r, 
        name="RNode_BT", 
        device=serial_port, 
        frequency=915000000, # Default (will be updated by hardware config)
        bandwidth=125000,
        txpower=7,
        sf=7,
        cr=5
    )
    r.interfaces.append(rnode_if)
    
    # 4. Setup LXMF
    id_path = os.path.join(config_dir, "storage", "identity")
    identity = RNS.Identity.from_file(id_path) if os.path.exists(id_path) else RNS.Identity()
    if not os.path.exists(id_path): identity.to_file(id_path)
    
    lxm_router = LXMF.LXMRouter(identity=identity, storagepath=config_dir)
    lxm_router.register_delivery_callback(message_received)
    
    return RNS.prettyhexrep(identity.hash)

def send_txt(dest_hex, text):
    try:
        dest_hash = bytes.fromhex(dest_hex)
        recipient = RNS.Destination(None, RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery")
        recipient.hash = dest_hash
        lxm = LXMF.LXMessage(recipient, lxm_router.identity, text)
        lxm_router.handle_outbound(lxm)
        return "Queued"
    except Exception as e: return str(e)

def get_inbox():
    global received_messages
    res = list(received_messages)
    received_messages = []
    return res