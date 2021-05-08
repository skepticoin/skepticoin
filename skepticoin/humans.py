"""
Tools to display hashes to humans.

We deviate from the bitcoin tradition, ostensibly inspired by shell games, of arbitrarily reverting bytes before
hexlifying them. We use plain old hexlify instead.
"""
from binascii import hexlify, unhexlify


def human(b: bytes) -> str:
    return hexlify(b).decode("utf-8")


def computer(s: str) -> bytes:
    return unhexlify(s.encode("utf-8"))


__all__ = ["human", "computer"]
