from scepticoin.signing import (
    PublicKey, SignableEquivalent, CoinbaseData, Signature, SECP256k1Signature, SECP256k1PublicKey)


def serialize_and_deserialize(thing, clz):
    other_thing = clz.deserialize(thing.serialize())
    assert thing == other_thing


def test_signable_equivalent_serialization():
    se = SignableEquivalent()
    serialize_and_deserialize(se, SignableEquivalent)


def test_coinbase_data_serialization():
    rd = CoinbaseData(1235, b"\x19\x88\x55")
    serialize_and_deserialize(rd, Signature)
    assert repr(rd) == 'CoinbaseData(1235, #198855)'


def test_coinbase_data_pretty_repr():
    rd = CoinbaseData(188, b"Don't trust the government, trust me instead.")
    assert repr(rd) == 'CoinbaseData(188, "Don\'t trust the government, trust me instead.")'


def test_signature_serialization():
    sig = SECP256k1Signature(b"a" * 64)
    serialize_and_deserialize(sig, Signature)


def test_publickey_serialization():
    pk = SECP256k1PublicKey(b"5" * 64)
    serialize_and_deserialize(pk, PublicKey)
