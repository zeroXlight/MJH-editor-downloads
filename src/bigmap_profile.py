"""Exact-build certification for the supplied mobile-world-map PC runtime."""
import hashlib
RACE_SHA='b029d553b2effba3b84868cf9e088d43f22bae825a0f51c0d04539698751ed1f'
CLIENT_SHA='a751183a3ec31af2fded561c0cb4a1ab56739d5197de575ac61dce016748099b'
NOV5_RACE_SHA='7b62233bd5b466868ba02996eb2bd1f44583d1fe83d0756f6361b58db5720c9b'
NOV15_RACE_SHA='aba6a72de4f31d82a891c273232e15382891585635ee15bcc28287702c877b8f'

def november15_parent(raw):
    return hashlib.sha256(raw).hexdigest()==NOV15_RACE_SHA

def november_parent(raw):
    return hashlib.sha256(raw).hexdigest()==NOV5_RACE_SHA
def race_parent(raw):
    if hashlib.sha256(raw).hexdigest() in (RACE_SHA,NOV5_RACE_SHA,NOV15_RACE_SHA):return True
    from shadow_bigmap import race_parent as certify
    return certify(raw)
def client_parent(raw):
    if hashlib.sha256(raw).hexdigest()==CLIENT_SHA:return True
    from shadow_bigmap import client_parent as certify
    return certify(raw)
def client_image(raw):
    if client_parent(raw):return True
    try:
        from shadow_bigmap import repair_legacy_client
        raw=repair_legacy_client(raw)
        from bigmap_martial_limit_enhance import normalize_client
        normalized,_=normalize_client(raw)
        from bigmap_pet_client_image import original
        return client_parent(original(normalized))
    except Exception:return False
def race_image(raw):
    if race_parent(raw):return True
    try:
        from growth_runtime import _original
        return race_parent(_original(raw))
    except Exception:return False
