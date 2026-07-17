#!/usr/bin/env python3
import subprocess
import uuid
import platform
import hashlib
import os
import json
import base64

# Paths
STORAGE_PATH = os.path.join(os.path.expanduser("~"), ".app_machine_id.json")
LICENSE_PATH = os.path.join(os.path.dirname(__file__), "license.key")   # adjust if needed

# ----------------------------------------------------------------------------
# Low-level helpers
# ----------------------------------------------------------------------------
def _save_data(data):
    try:
        with open(STORAGE_PATH, "w") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass

def _load_data():
    try:
        if os.path.exists(STORAGE_PATH):
            with open(STORAGE_PATH, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return None

# ----------------------------------------------------------------------------
# Hardware fingerprint (stable)
# ----------------------------------------------------------------------------
def _get_hardware_fingerprint():
    identifiers = []
    system = platform.system()

    # Linux
    if system == "Linux":
        for path in ["/etc/machine-id", "/var/lib/dbus/machine-id"]:
            try:
                with open(path, "r") as f:
                    mid = f.read().strip()
                    if mid:
                        identifiers.append(mid)
                        break
            except Exception:
                continue

    # Windows
    elif system == "Windows":
        try:
            output = subprocess.check_output(
                "wmic csproduct get uuid", shell=True, encoding="utf-8"
            ).strip()
            lines = [line.strip() for line in output.split("\n") if line.strip()]
            if len(lines) >= 2:
                uuid_val = lines[1]
                if uuid_val and uuid_val.upper() != "TO BE FILLED BY O.E.M.":
                    identifiers.append(uuid_val)
        except Exception:
            pass

    # macOS
    elif system == "Darwin":
        try:
            output = subprocess.check_output(
                "ioreg -rd1 -c IOPlatformExpertDevice | grep IOPlatformUUID",
                shell=True,
                encoding="utf-8",
            ).strip()
            if "=" in output:
                uuid_val = output.split("=")[1].strip().strip('"')
                identifiers.append(uuid_val)
        except Exception:
            pass

    # Fallback to MAC address (stable on most systems)
    if not identifiers:
        mac = uuid.getnode()
        # Convert to string – even if it's a random value (0xFFFFFFFFFFFF) we still use it
        # because it's better than a random UUID that changes each time.
        identifiers.append(str(mac))

    # Last resort (should never happen, but keep for safety)
    if not identifiers:
        identifiers.append(str(uuid.uuid4()))

    combined = "|".join(identifiers)
    return hashlib.sha256(combined.encode()).hexdigest()

# ----------------------------------------------------------------------------
# Extract machine ID from an existing license (if present)
# ----------------------------------------------------------------------------
def _extract_machine_id_from_license():
    if not os.path.exists(LICENSE_PATH):
        return None

    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives.serialization import load_pem_public_key
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding as Padding

    PUBLIC_KEY_PEM = b"""-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAnPZPUM+c6Ph7eESpgeWZ
pyCSb9bvX8oIieWr6A1aZpvSHo+26E0Pd3DzUxEOEjhh36UpjPX7DG2rPA9nQHOM
nQLBhqD8e3jRU8RfxVynsqSh6S4SHOCrygD6isRGiyqeYceYTTpB7fJ4DOHzQ2MY
34R/D+pfHcF09KLqLlKtSuZ4thM3Wj1ssPi6vOdukCrDh1NrWS6nTiqfT/yBvg5B
aAmjibsM3lJ0mMsYWY4m2yf7TqviFoKa3+cBdbnFo5ydPmJvg3dk4Zsijn4F0STN
w8gcIHo9n7XMeixN261we9kHZM6Ha4PMBsDkP00XQbe0paBN+pLFsiqy2N9XH+8p
MwIDAQAB
-----END PUBLIC KEY-----"""

    try:
        with open(LICENSE_PATH, "r") as f:
            license_data = json.load(f)
        data = base64.b64decode(license_data["data"])
        signature = base64.b64decode(license_data["signature"])
        public_key = load_pem_public_key(PUBLIC_KEY_PEM, backend=default_backend())
        public_key.verify(
            signature,
            data,
            Padding.PSS(
                mgf=Padding.MGF1(hashes.SHA256()),
                salt_length=Padding.PSS.MAX_LENGTH
            ),
            hashes.SHA256()
        )
        payload = json.loads(data.decode())
        return payload.get("machine_id")
    except Exception:
        return None

# ----------------------------------------------------------------------------
# Public API: get stable machine ID
# ----------------------------------------------------------------------------
def get_machine_id():
    """
    Returns the persistent machine ID (or None if hardware mismatch is detected).
    Migration:
      - If no stored data but a valid license exists, the license's machine ID
        is used as the persistent ID (so existing licenses keep working).
      - If old stored data lacks a fingerprint, the fingerprint is added.
    """
    stored = _load_data()
    current_fingerprint = _get_hardware_fingerprint()

    # ---- No stored data ----
    if stored is None:
        # Try to get the ID from an existing license (backward compatibility)
        license_mid = _extract_machine_id_from_license()
        if license_mid is not None:
            # Use the license's machine ID as the persistent ID
            _save_data({
                "machine_id": license_mid,
                "fingerprint": current_fingerprint
            })
            return license_mid

        # No license – generate new ID from fingerprint
        machine_id = current_fingerprint
        _save_data({
            "machine_id": machine_id,
            "fingerprint": current_fingerprint
        })
        return machine_id

    # ---- Stored data exists ----
    stored_id = stored.get("machine_id")
    stored_fp = stored.get("fingerprint")

    # If old data without fingerprint (from a previous version), migrate
    if stored_fp is None:
        _save_data({
            "machine_id": stored_id,
            "fingerprint": current_fingerprint
        })
        return stored_id

    # Full data: verify fingerprint
    if stored_fp != current_fingerprint:
        # Hardware mismatch – likely the folder was copied to another machine
        return None

    return stored_id