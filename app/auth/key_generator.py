import hashlib
import secrets


def generate_api_key():

    raw_key = (
        "ecom_live_"
        + secrets.token_urlsafe(32)
    )

    key_hash = hashlib.sha256(
        raw_key.encode()
    ).hexdigest()

    return raw_key, key_hash
