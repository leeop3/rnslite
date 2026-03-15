import json
import os

_PATH = "/data/data/com.leeop3.rnslite/files/contacts.json"

def get_all():
    if os.path.exists(_PATH):
        try:
            with open(_PATH, "r") as f: return json.load(f)
        except: return []
    return []

def save(hash_hex, name):
    contacts = get_all()
    for c in contacts:
        if c["hash"] == hash_hex:
            c["name"] = name
            break
    else:
        contacts.append({"hash": hash_hex, "name": name})
    with open(_PATH, "w") as f: json.dump(contacts, f)

def resolve(hash_hex, fallback):
    for c in get_all():
        if c["hash"] == hash_hex: return c["name"]
    return fallback