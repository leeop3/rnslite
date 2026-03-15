import RNS
import LXMF
import os
import threading
import time
import base64
from RNS.Interfaces.Interface import Interface

# Custom Interface for Bluetooth
class BTInterface(Interface):
    def __init__(self, owner, name, bt_wrapper):
        super().__init__(owner, name)
        self.bt = bt_wrapper
        self.online = True
    def send_bin(self, data):
        try: self.bt.write(data)
        except: pass
    def read_loop(self):
        while self.online:
            try:
                data = self.bt.read(1024)
                if data: self.owner.inbound(data, self)
            except: time.sleep(0.1)

lxm_router = None
received_messages = []

# Callback for incoming LXMF messages
def message_received(lxm):
    sender = RNS.prettyhexrep(lxm.source_hash)
    content = lxm.content.decode("utf-8") if isinstance(lxm.content, bytes) else lxm.content
    # Check if there is an image (Sideband style attachment logic)
    has_image = "Yes" if lxm.fields and "image" in lxm.fields else "No"
    received_messages.append({"sender": sender, "content": content, "image": has_image})

def start(bt_wrapper):
    global lxm_router
    storage = RNS.Reticulum.configdir
    RNS.Reticulum()
    
    # Init BT Interface
    bt_if = BTInterface(RNS.Reticulum.get_instance(), "RNode_BT", bt_wrapper)
    RNS.Reticulum.get_instance().interfaces.append(bt_if)
    threading.Thread(target=bt_if.read_loop, daemon=True).start()
    
    # Init LXMF
    identity_path = os.path.join(storage, "identity")
    if os.path.exists(identity_path):
        local_identity = RNS.Identity.from_file(identity_path)
    else:
        local_identity = RNS.Identity()
        local_identity.to_file(identity_path)
        
    lxm_router = LXMF.LXMRouter(identity=local_identity, storagepath=storage)
    lxm_router.register_delivery_callback(message_received)
    
    return RNS.prettyhexrep(local_identity.hash)

def send_txt(dest_hex, text):
    try:
        dest_hash = bytes.fromhex(dest_hex)
        recipient = RNS.Destination(None, RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery")
        recipient.hash = dest_hash
        lxm = LXMF.LXMessage(recipient, lxm_router.identity, text, title="RNS Lite Msg")
        lxm_router.handle_outbound(lxm)
        return "Message Queued"
    except Exception as e: return str(e)

def send_img(dest_hex, img_b64):
    try:
        dest_hash = bytes.fromhex(dest_hex)
        img_data = base64.b64decode(img_b64)
        recipient = RNS.Destination(None, RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery")
        recipient.hash = dest_hash
        
        # Attach image to LXMF fields (Sideband compatible)
        lxm = LXMF.LXMessage(recipient, lxm_router.identity, "Sent an image")
        lxm.fields["image"] = img_data
        lxm_router.handle_outbound(lxm)
        return "Image Queued"
    except Exception as e: return str(e)

def get_inbox():
    global received_messages
    msgs = list(received_messages)
    received_messages = [] # Clear after reading
    return msgs