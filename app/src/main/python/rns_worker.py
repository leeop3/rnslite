import RNS
import LXMF
import os
import threading
from RNS.Interfaces.Interface import Interface

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
            data = self.bt.read(512)
            if data: self.owner.inbound(data, self)

lxm_router = None

def start(bt_wrapper):
    global lxm_router
    # Use the app internal files dir (provided by RNS.Reticulum default logic in Chaquopy)
    RNS.Reticulum()
    
    bt_if = BTInterface(RNS.Reticulum.get_instance(), "RNode_BT", bt_wrapper)
    RNS.Reticulum.get_instance().interfaces.append(bt_if)
    
    identity = RNS.Identity()
    lxm_router = LXMF.LXMRouter(identity=identity, storagepath=RNS.Reticulum.configdir)
    
    threading.Thread(target=bt_if.read_loop, daemon=True).start()
    return "RNS Online"

def send_message(dest_hex, text):
    try:
        dest_hash = bytes.fromhex(dest_hex)
        recipient = RNS.Destination(None, RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery")
        recipient.hash = dest_hash
        lxm = LXMF.LXMessage(recipient, lxm_router.identity, text)
        lxm_router.handle_outbound(lxm)
        return "Sent"
    except Exception as e: return str(e)