"""Small RFC 6238-compatible TOTP verifier used when MFA is enabled."""

import base64
import hashlib
import hmac
import struct
import time


def verify_totp(secret, token, now=None, window=1):
    if not secret or not token or not str(token).isdigit():
        return False
    try:
        key = base64.b32decode(secret.upper())
    except Exception:  # malformed user-provided/encrypted-at-rest secret
        return False
    counter = int(now or time.time()) // 30
    for offset in range(-window, window + 1):
        digest = hmac.new(key, struct.pack(">Q", counter + offset), hashlib.sha1).digest()
        index = digest[-1] & 15
        code = (struct.unpack(">I", digest[index : index + 4])[0] & 0x7FFFFFFF) % 1_000_000
        if hmac.compare_digest(f"{code:06d}", str(token)):
            return True
    return False
