"""Access key validation."""

import os


def validate_access_key(key: str) -> bool:
    """Check if key is in the VALID_ACCESS_KEYS env var (comma-separated list).

    Returns True if key is valid, False otherwise.
    """
    valid_keys_raw = os.getenv("VALID_ACCESS_KEYS", "")
    valid_keys = {k.strip() for k in valid_keys_raw.split(",") if k.strip()}
    return key.strip() in valid_keys
