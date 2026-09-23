"""Stdlib, strict: rejects anything outside the alphabet."""
import base64


def encode(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")


def decode(s: str) -> bytes:
    return base64.b64decode(s, validate=True)
