"""
Maximum removal of smoke and mirrors. This means:

* No fancy (though mostly unused) scripts here as in bitcoin. We stick to the core business: claiming by signing.
* There's no equivalent of a "bitcoin addresses", P2PKH or P2SH: just public keys and signatures.

One byte is reserved as a type_indicator if we ever want to offer more options (compressed public keys anyone?)
"""
import struct
import ecdsa  # NOTE "This library was not designed with security in mind."

from .humans import human
from .serialization import Serializable, DeserializationError, safe_read

TYPE_SIGNABLE_EQUIVALENT = b'\x00'
TYPE_COINBASE_DATA = b'\x01'
TYPE_SECP256k1 = b'\x02'


class PublicKey(Serializable):

    @classmethod
    def stream_deserialize(cls, f):
        type_indicator = safe_read(f, 1)

        if type_indicator == TYPE_SECP256k1:
            return SECP256k1PublicKey.stream_deserialize(f)

        raise DeserializationError("Non-supported public key type.")


class SECP256k1PublicKey(PublicKey):
    """We use the same curve as bitcoin because why not. Remember: the NIST curves were chosen by the lizard people!"""

    def __init__(self, public_key):
        if not len(public_key) == 64:
            raise ValueError('SECP256k1 public key must be 64 bytes.')

        self.public_key = public_key

    def __repr__(self):
        return "SECP256k1 Public Key %s" % human(self.public_key)

    def __eq__(self, other):
        return isinstance(other, SECP256k1PublicKey) and self.public_key == other.public_key

    def __hash__(self):
        return hash(self.serialize())

    @classmethod
    def stream_deserialize(cls, f):
        # type_indicator has been read already by the superclass at this point.
        public_key = safe_read(f, 64)
        return cls(public_key)

    def stream_serialize(self, f):
        f.write(TYPE_SECP256k1)
        f.write(self.public_key)

    def validate(self, signature, message):
        if not isinstance(signature, SECP256k1Signature):
            return False

        vk = ecdsa.VerifyingKey.from_string(self.public_key, curve=ecdsa.SECP256k1)
        try:
            vk.verify(signature.signature, message)
            return True
        except ecdsa.keys.BadSignatureError:
            return False


class Signature(Serializable):

    @classmethod
    def stream_deserialize(cls, f):
        type_indicator = safe_read(f, 1)

        if type_indicator == TYPE_SIGNABLE_EQUIVALENT:
            return SignableEquivalent.stream_deserialize(f)

        if type_indicator == TYPE_COINBASE_DATA:
            return CoinbaseData.stream_deserialize(f)

        if type_indicator == TYPE_SECP256k1:
            return SECP256k1Signature.stream_deserialize(f)

        raise DeserializationError("Non-supported signature type.")

    def is_not_signature(self):
        """In various places where signatures are expected, special-meaning placeholders can occur instead. Signatures
        that may actually be used to verify public keys should return False here."""
        return True


class SignableEquivalent(Signature):
    """SignableEquivalent: when signing transactions you can't sign your own signature."""

    def __repr__(self):
        return 'SignableEquivalent()'

    def __eq__(self, other):
        return isinstance(other, SignableEquivalent)

    @classmethod
    def stream_deserialize(cls, f):
        # type_indicator has been read already by the superclass at this point.
        return cls()

    def stream_serialize(self, f):
        f.write(TYPE_SIGNABLE_EQUIVALENT)


class CoinbaseData(Signature):
    """In Coinbase transactions, some random data takes the place of the signature. This may be used by miners to
    introduce extra randomness if the nonce is not enough, or to include pseudo-polical messages."""

    def __init__(self, height, signature):
        if not (0 <= height <= 0xffffffff):
            raise ValueError('CoinbaseData height out of range.' % height)

        if len(signature) > 256:
            raise ValueError("Unserializable CoinbaseData")

        # height is included to make guarantee Transaction uniqueness. (without height, mining a block with a single
        # coinbase transaction with the same output address twice would lead to non-uniqueness).
        self.height = height
        self.signature = signature

    def __repr__(self):
        if all([32 <= b < 127 for b in self.signature]):
            return 'CoinbaseData(%s, "%s")' % (self.height, str(self.signature, encoding="ascii"))
        return 'CoinbaseData(%s, #%s)' % (self.height, human(self.signature))

    def __eq__(self, other):
        return isinstance(other, CoinbaseData) and self.signature == other.signature

    @classmethod
    def stream_deserialize(cls, f):
        # type_indicator has been read already by the superclass at this point.
        (height,) = struct.unpack(b">I", safe_read(f, 4))
        (length,) = struct.unpack(b"B", safe_read(f, 1))
        signature = safe_read(f, length)
        return cls(height, signature)

    def stream_serialize(self, f):
        f.write(TYPE_COINBASE_DATA)
        f.write(struct.pack(b">I", self.height))
        f.write(struct.pack(b"B", len(self.signature)))
        f.write(self.signature)


class SECP256k1Signature(Signature):

    def __init__(self, signature):
        if not len(signature) == 64:
            raise ValueError('SECP256k1 signature must be 64 bytes.')

        self.signature = signature

    def __repr__(self):
        return "SECP256k1 Signature %s" % human(self.signature)

    def __eq__(self, other):
        return isinstance(other, SECP256k1Signature) and self.signature == other.signature

    @classmethod
    def stream_deserialize(cls, f):
        # type_indicator has been read already by the superclass at this point.
        signature = safe_read(f, 64)
        return cls(signature)

    def stream_serialize(self, f):
        f.write(TYPE_SECP256k1)
        f.write(self.signature)

    def validate(self, public_key, message):
        if not isinstance(public_key, SECP256k1PublicKey):
            return False

        return public_key.validate(self, message)

    def is_not_signature(self):
        return False


__all__ = [
    "PublicKey",
    "SECP256k1PublicKey",
    "Signature",
    "SignableEquivalent",
    "CoinbaseData",
    "SECP256k1Signature",
]
