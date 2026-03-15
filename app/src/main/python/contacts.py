import json
import os

PATH = "/data/data/com.leeop3.rnslite/files/contacts.json"

def get_all():
    if os.path.exists(PATH):
        with open(PATH, "r") as f: return json.load(f)
    return []

def save(hash_hex, name):
    contacts = get_all()
    # Update if exists, else append
    for c in contacts:
        if c["hash"] == hash_hex:
            c["name"] = name
            break
    else:
        contacts.append({"hash": hash_hex, "name": name})
    with open(PATH, "w") as f: json.dump(contacts, f)

def resolve(hash_hex, fallback):
    for c in get_all():
        if c["hash"] == hash_hex: return c["name"]
    return fallback