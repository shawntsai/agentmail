"""Cryptographic identity, signing, and encryption using PyNaCl.

Each node has:
- Ed25519 signing key (identity + message signing)
- Curve25519 key derived from Ed25519 (for encryption via sealed boxes)
"""

import json
import os
from base64 import b64decode, b64encode

from nacl.encoding import Base64Encoder
from nacl.public import PrivateKey, PublicKey, SealedBox
from nacl.signing import SigningKey, VerifyKey
from nacl.utils import random


class Identity:
    """A node's cryptographic identity."""

    def __init__(self, signing_key: SigningKey):
        self._signing_key = signing_key
        self.verify_key = signing_key.verify_key
        # Derive Curve25519 keys for encryption
        self._encrypt_private = signing_key.to_curve25519_private_key()
        self.encrypt_public = self.verify_key.to_curve25519_public_key()

    @classmethod
    def generate(cls) -> "Identity":
        return cls(SigningKey.generate())

    @classmethod
    def from_file(cls, path: str) -> "Identity":
        with open(path, "r") as f:
            data = json.load(f)
        seed = b64decode(data["signing_seed"])
        return cls(SigningKey(seed))

    def save(self, path: str):
        data = {
            "signing_seed": b64encode(bytes(self._signing_key)).decode(),
            "verify_key": self.pubkey_b64,
            "encrypt_pubkey": b64encode(bytes(self.encrypt_public)).decode(),
        }
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)

    @classmethod
    def load_or_create(cls, path: str) -> "Identity":
        if os.path.exists(path):
            return cls.from_file(path)
        identity = cls.generate()
        identity.save(path)
        return identity

    @property
    def pubkey_b64(self) -> str:
        return b64encode(bytes(self.verify_key)).decode()

    @property
    def encrypt_pubkey_b64(self) -> str:
        return b64encode(bytes(self.encrypt_public)).decode()

    @property
    def fingerprint(self) -> str:
        """Short URL-safe fingerprint for display and relay routing."""
        from base64 import urlsafe_b64encode
        return urlsafe_b64encode(bytes(self.verify_key)).decode()[:16]

    def sign(self, data: bytes) -> str:
        """Sign data, return base64 signature."""
        signed = self._signing_key.sign(data)
        return b64encode(signed.signature).decode()

    @staticmethod
    def verify(data: bytes, signature_b64: str, pubkey_b64: str) -> bool:
        """Verify a signature."""
        try:
            sig = b64decode(signature_b64)
            vk = VerifyKey(b64decode(pubkey_b64))
            vk.verify(data, sig)
            return True
        except Exception:
            return False

    def encrypt_for(self, plaintext: bytes, recipient_pubkey_b64: str) -> str:
        """Encrypt data for a recipient using their public key (sealed box)."""
        recipient_pk = PublicKey(b64decode(recipient_pubkey_b64))
        sealed_box = SealedBox(recipient_pk)
        encrypted = sealed_box.encrypt(plaintext)
        return b64encode(encrypted).decode()

    def decrypt(self, ciphertext_b64: str) -> bytes:
        """Decrypt data sent to us via sealed box."""
        sealed_box = SealedBox(self._encrypt_private)
        return sealed_box.decrypt(b64decode(ciphertext_b64))
