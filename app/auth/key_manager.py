import hashlib
import secrets


def generate_api_key():

    secret = secrets.token_urlsafe(
        32
    )

    raw_key = (
        f"sk_live_{secret}"
    )

    key_hash = hashlib.sha256(
        raw_key.encode()
    ).hexdigest()

    return raw_key, key_hash
