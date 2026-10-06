"""A software passkey for tests: does what a phone or laptop would do."""

import hashlib
import json
import os
import struct

import cbor2
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from webauthn.helpers import bytes_to_base64url

USER_PRESENT, USER_VERIFIED, HAS_CREDENTIAL = 0x01, 0x04, 0x40


class SoftAuthenticator:
    def __init__(self, origin="http://testserver", rp_id="testserver"):
        self.origin, self.rp_id = origin, rp_id
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.credential_id = os.urandom(32)
        self.counter = 0
        self.user_handle = None

    def _client_data(self, kind, challenge):
        return json.dumps(
            {"type": kind, "challenge": challenge, "origin": self.origin, "crossOrigin": False}
        ).encode()

    def _auth_data(self, flags, attested=b""):
        self.counter += 1
        return (
            hashlib.sha256(self.rp_id.encode()).digest()
            + bytes([flags])
            + struct.pack(">I", self.counter)
            + attested
        )

    def create(self, options, verified=True):
        """Answer a registration challenge (navigator.credentials.create)."""
        numbers = self.key.public_key().public_numbers()
        cose_key = cbor2.dumps(
            {
                1: 2,
                3: -7,
                -1: 1,
                -2: numbers.x.to_bytes(32, "big"),
                -3: numbers.y.to_bytes(32, "big"),
            }
        )
        attested = (
            bytes(16) + struct.pack(">H", len(self.credential_id)) + self.credential_id + cose_key
        )
        flags = USER_PRESENT | HAS_CREDENTIAL | (USER_VERIFIED if verified else 0)
        auth_data = self._auth_data(flags, attested)
        self.user_handle = options["user"]["id"]
        return {
            "id": bytes_to_base64url(self.credential_id),
            "rawId": bytes_to_base64url(self.credential_id),
            "type": "public-key",
            "clientExtensionResults": {},
            "response": {
                "clientDataJSON": bytes_to_base64url(
                    self._client_data("webauthn.create", options["challenge"])
                ),
                "attestationObject": bytes_to_base64url(
                    cbor2.dumps({"fmt": "none", "attStmt": {}, "authData": auth_data})
                ),
            },
        }

    def get(self, options, verified=True):
        """Answer a sign-in challenge (navigator.credentials.get)."""
        client_data = self._client_data("webauthn.get", options["challenge"])
        auth_data = self._auth_data(USER_PRESENT | (USER_VERIFIED if verified else 0))
        signature = self.key.sign(
            auth_data + hashlib.sha256(client_data).digest(), ec.ECDSA(hashes.SHA256())
        )
        return {
            "id": bytes_to_base64url(self.credential_id),
            "rawId": bytes_to_base64url(self.credential_id),
            "type": "public-key",
            "clientExtensionResults": {},
            "response": {
                "clientDataJSON": bytes_to_base64url(client_data),
                "authenticatorData": bytes_to_base64url(auth_data),
                "signature": bytes_to_base64url(signature),
                "userHandle": self.user_handle,
            },
        }
