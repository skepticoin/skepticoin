from skepticoin.signing import SECP256k1Signature, SECP256k1PublicKey
from skepticoin.datatypes import (
    Block,
    BlockHeader,
    BlockSummary,
    Input,
    Output,
    OutputReference,
    PowEvidence,
    Transaction,
)
from skepticoin.humans import computer


def serialize_and_deserialize(thing):
    other_thing = type(thing).deserialize(thing.serialize())
    assert thing == other_thing


def test_output_reference_serialization():
    ref = OutputReference(b"a" * 32, 1234)
    serialize_and_deserialize(ref)


def test_input_serialization():
    inp = Input(
        output_reference=OutputReference(b"b" * 32, 1234),
        signature=SECP256k1Signature(b"b" * 64),
    )
    serialize_and_deserialize(inp)


def test_output_serialization():
    out = Output(
        value=1582,
        public_key=SECP256k1PublicKey(b"g" * 64),
    )
    serialize_and_deserialize(out)


def test_transaction_serialization():
    trans = Transaction(
        inputs=[Input(output_reference=OutputReference(b"b" * 32, 1234), signature=SECP256k1Signature(b"b" * 64))],
        outputs=[Output(value=1582, public_key=SECP256k1PublicKey(b"g" * 64))],
    )
    serialize_and_deserialize(trans)


def test_transaction_repr():
    trans = Transaction(
        inputs=[Input(output_reference=OutputReference(b"b" * 32, 1234), signature=SECP256k1Signature(b"b" * 64))],
        outputs=[Output(value=1582, public_key=SECP256k1PublicKey(b"g" * 64))],
    )

    assert repr(trans) == "Transaction #4025f3f13790dc96d857562dabcdd257ee9dfd95ce126e11d8cbbe64ac1bbec4"


example_block_summary = BlockSummary(
    height=445,
    previous_block_hash=b"a" * 32,
    merkle_root_hash=b"b" * 32,
    timestamp=1231006505,
    target=computer("00000000ffff0000000000000000000000000000000000000000000000000000"),
    nonce=1234,
)


def test_block_summary_serialization():
    serialize_and_deserialize(example_block_summary)


example_pow_evidence = PowEvidence(
    summary_hash=b"d" * 32,
    chain_sample=b"e" * 32,
    block_hash=b"f" * 32,
)


def test_pow_evidence_serialization():
    serialize_and_deserialize(example_pow_evidence)


def test_block_header_serialization():
    bh = BlockHeader(
        summary=example_block_summary,
        pow_evidence=example_pow_evidence,
    )
    serialize_and_deserialize(bh)


def test_block_serialization():
    block = Block(
        header=BlockHeader(
            summary=example_block_summary,
            pow_evidence=example_pow_evidence,
        ),
        transactions=[Transaction(
            inputs=[Input(output_reference=OutputReference(b"b" * 32, 1234), signature=SECP256k1Signature(b"b" * 64))],
            outputs=[Output(value=1582, public_key=SECP256k1PublicKey(b"g" * 64))],
        )] * 2,
    )

    serialize_and_deserialize(block)
