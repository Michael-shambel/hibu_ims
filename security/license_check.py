#!/usr/bin/env python3
import json
import base64
import os
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding as Padding
from . import hardware_id

PUBLIC_KEY_PEM = b"""-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA0OwoAK8r3NInwc66SfA+
qG6FZcqT7XFpUN3X/Sf+iRtijWpA54QJFQyBuMusNpMcQVtmxsCzglHBqWE7ez3W
4AOfXotD+idD6yU+Ry56oUxqBy/fmh9PnI1DQ6OtxyQoFuD/ngkjB/VVELuRCFpK
8aTc86DbDK2fXNx+UAXlRacDTMvtdjl1nnJssqYEeRKX3xkMJlnJPAcGHT5YBTRc
zZkDVbmBprpzZ1OXse3iSQnriW0/ukO9dwKLOduRcajgqGh22AMjgHzFfcn2HJw6
SSvTh6ayGTW7gJU5LEVcLlf4/3LPNk20nGKWIfE9jy1vndYs06YFBc3Rd3AVw5Wl
TwIDAQAB
-----END PUBLIC KEY-----"""

def verify_license(license_path="license.key"):
    # 1. Load public key
    try:
        public_key = load_pem_public_key(PUBLIC_KEY_PEM, backend=default_backend())
    except Exception as e:
        return False, f"Failed to load public key: {e}"

    # 2. Check license file existence
    if not os.path.exists(license_path):
        mid = hardware_id.get_machine_id()
        if mid is None:
            mid = "Unable to determine machine ID (hardware mismatch)"
        return False, f"License file not found.\nYour machine ID is:\n{mid}\nPlease send this ID to the software provider to obtain a valid license."

    # 3. Read and decode license
    try:
        with open(license_path, "r") as f:
            license_data = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        return False, "License file is corrupted."

    try:
        data = base64.b64decode(license_data["data"])
        signature = base64.b64decode(license_data["signature"])
    except (KeyError, ValueError) as e:
        return False, "Invalid license file format."

    # 4. Verify signature
    try:
        public_key.verify(
            signature,
            data,
            Padding.PSS(
                mgf=Padding.MGF1(hashes.SHA256()),
                salt_length=Padding.PSS.MAX_LENGTH
            ),
            hashes.SHA256()
        )
    except Exception as e:
        return False, "License signature invalid."

    # 5. Decode payload
    try:
        payload = json.loads(data.decode())
    except json.JSONDecodeError:
        return False, "License data corrupted."

    # 6. Get current machine ID (now may return None)
    current_id = hardware_id.get_machine_id()

    # 7. Check environment tampering
    if current_id is None:
        return False, "Environment mismatch detected. This license cannot be used on this machine."

    # 8. Compare IDs
    expected_id = payload.get("machine_id")
    if expected_id != current_id:
        return False, "This license is not valid for this computer."

    return True, "License is valid."