import struct

from .humans import human
from .serialization import (
    safe_read,
    Serializable,
    stream_deserialize_list,
    stream_deserialize_vlq,
    stream_serialize_list,
    stream_serialize_vlq,
)
from .signing import Signature, PublicKey, SignableEquivalent
from .hash import sha256d
from .params import CHAIN_SAMPLE_TOTAL_SIZE


class OutputReference(Serializable):
    """Refer an output by its transaction hash and index into its list of outputs."""

    def __init__(self, hash, index):
        if not len(hash) == 32:
            raise ValueError('OutputReference hash must be 32 bytes.')

        if not (0 <= index <= 0xffffffff):
            raise ValueError('OutputReference index out of range.' % index)

        self.hash = hash
        self.index = index

    def __repr__(self):
        return "OutputReference(%s, %s)" % (human(self.hash), self.index)

    def __eq__(self, other):
        return self.hash == other.hash and self.index == other.index

    def __hash__(self):
        return hash((self.hash, self.index))

    @classmethod
    def stream_deserialize(cls, f):
        hash = safe_read(f, 32)
        (index,) = struct.unpack(b">I", safe_read(f, 4))
        return cls(hash, index)

    def stream_serialize(self, f):
        f.write(self.hash)
        f.write(struct.pack(b">I", self.index))

    def references_thin_air(self):
        return (self.hash == b'\x00' * 32) and (self.index == 0)


class Input(Serializable):
    """Input of a transaction"""

    def __init__(self, output_reference, signature):
        # bitcoin's sequence number (unused) is not reproduced here. See
        # https://bitcoin.stackexchange.com/questions/2025/what-is-txins-sequence

        self.output_reference = output_reference
        self.signature = signature

    def __repr__(self):
        return "Input(%s, %s)" % (self.output_reference, self.signature)

    def __eq__(self, other):
        return self.output_reference == other.output_reference and self.signature == other.signature

    @classmethod
    def stream_deserialize(cls, f):
        output_reference = OutputReference.stream_deserialize(f)
        signature = Signature.stream_deserialize(f)
        return cls(output_reference, signature)

    def stream_serialize(self, f):
        self.output_reference.stream_serialize(f)
        self.signature.stream_serialize(f)

    def signable_equivalent(self):
        # we simply replace the signature with a SignableEquivalent (which serializes to a type-byte)
        return Input(
            output_reference=self.output_reference,
            signature=SignableEquivalent()
        )


class Output(Serializable):
    """Output of a transaction."""

    def __init__(self, value, public_key):
        self.value = value
        self.public_key = public_key

    def __repr__(self):
        return "Output(%s, %s)" % (self.value, self.public_key)

    def __eq__(self, other):
        return self.value == other.value and self.public_key == other.public_key

    @classmethod
    def stream_deserialize(cls, f):
        (value,) = struct.unpack(b">Q", safe_read(f, 8))
        public_key = PublicKey.stream_deserialize(f)
        return cls(value, public_key)

    def stream_serialize(self, f):
        f.write(struct.pack(b">Q", self.value))
        self.public_key.stream_serialize(f)


class Transaction(Serializable):

    def __init__(self, inputs, outputs):
        self.version = 0  # reserved for future use; the class does not take this as a param.
        self.inputs = inputs
        self.outputs = outputs

    def __repr__(self):
        return "Transaction #%s" % human(self.hash())

    def __eq__(self, other):
        return self.inputs == other.inputs and self.outputs == other.outputs

    @classmethod
    def stream_deserialize(cls, f):
        if safe_read(f, 1) != b'\x00':
            raise ValueError("Current version supports only version 0 transactions")

        inputs = stream_deserialize_list(f, Input)
        outputs = stream_deserialize_list(f, Output)
        return cls(inputs, outputs)

    def stream_serialize(self, f):
        f.write(struct.pack(b"B", self.version))
        stream_serialize_list(f, self.inputs)
        stream_serialize_list(f, self.outputs)

    def hash(self):
        return sha256d(self.serialize())

    def __hash__(self):
        return hash(self.hash())

    def signable_equivalent(self):
        # Because transactions contain (in their inputs) signatures, they cannot be signed as-is (you would need to know
        # the signature). So we sign a thing with the signatures taken out instead.
        return Transaction(
            inputs=[input.signable_equivalent() for input in self.inputs],
            outputs=self.outputs,
        )


class PowEvidence(Serializable):

    def __init__(self, summary_hash, chain_sample, block_hash):
        self.summary_hash = summary_hash
        self.chain_sample = chain_sample
        self.block_hash = block_hash

    def __repr__(self):
        return "PowEvidence(%s %s %s)" % (
            human(self.summary_hash),
            human(self.chain_sample),
            human(self.block_hash),
            )

    def __eq__(self, other):
        return (
            isinstance(other, PowEvidence) and
            self.summary_hash == other.summary_hash and
            self.chain_sample == other.chain_sample and
            self.block_hash == other.block_hash
        )

    @classmethod
    def stream_deserialize(cls, f):
        summary_hash = safe_read(f, 32)
        chain_sample = safe_read(f, CHAIN_SAMPLE_TOTAL_SIZE)
        block_hash = safe_read(f, 32)

        return cls(summary_hash, chain_sample, block_hash)

    def stream_serialize(self, f):
        f.write(self.summary_hash)
        f.write(self.chain_sample)
        f.write(self.block_hash)


class BlockSummary(Serializable):
    # akin to Bitcoin's BlockHeader. Our BlockHeader contains an PowEvidence also though, so we need an extra layer

    def __init__(self, height, previous_block_hash, merkle_root_hash, timestamp, target, nonce):
        # block height is included here to allow for partial validation of the POW in absence of the full block. (block
        # height is needed to calculate the blocks to sample from in chain_sample).
        self.height = height

        self.previous_block_hash = previous_block_hash
        self.merkle_root_hash = merkle_root_hash
        self.timestamp = timestamp

        # the `target`, i.e. the upper bound for the block's hash. We store this directly as a 32-byte rather than using
        # e.g. bitcoin's "bits" (which is yet another thing to understand/explain).
        self.target = target
        self.nonce = nonce  # it could be argued that this should be in PowEvidence

    def __repr__(self):
        return "BlockSummary #%s" % human(self.hash())

    def __eq__(self, other):
        return (
            isinstance(other, BlockSummary) and
            self.previous_block_hash == other.previous_block_hash and
            self.merkle_root_hash == other.merkle_root_hash and
            self.timestamp == other.timestamp and
            self.target == other.target and
            self.nonce == other.nonce
        )

    @classmethod
    def stream_deserialize(cls, f):
        height = stream_deserialize_vlq(f)
        previous_block_hash = safe_read(f, 32)
        merkle_root_hash = safe_read(f, 32)
        (timestamp,) = struct.unpack(b">I", safe_read(f, 4))
        target = safe_read(f, 32)
        (nonce,) = struct.unpack(b">I", safe_read(f, 4))

        return cls(height, previous_block_hash, merkle_root_hash, timestamp, target, nonce)

    def stream_serialize(self, f):
        stream_serialize_vlq(f, self.height)
        f.write(self.previous_block_hash)
        f.write(self.merkle_root_hash)
        f.write(struct.pack(b">I", self.timestamp))
        f.write(self.target)
        f.write(struct.pack(b">I", self.nonce))

    def hash(self):
        return sha256d(self.serialize())


class BlockHeader(Serializable):

    def __init__(self, summary, pow_evidence):
        self.version = 0
        self.summary = summary
        self.pow_evidence = pow_evidence

    def __repr__(self):
        return "BlockHeader #%s" % human(self.hash())

    def __eq__(self, other):
        return (
            isinstance(other, BlockHeader) and
            self.summary == other.summary and
            self.pow_evidence == other.pow_evidence
        )

    @classmethod
    def stream_deserialize(cls, f):
        if safe_read(f, 1) != b'\x00':
            raise ValueError("Current version only supports version 0 blocks")

        summary = BlockSummary.stream_deserialize(f)
        pow_evidence = PowEvidence.stream_deserialize(f)

        return cls(summary, pow_evidence)

    def stream_serialize(self, f):
        f.write(struct.pack(b"B", self.version))

        self.summary.stream_serialize(f)
        self.pow_evidence.stream_serialize(f)

    def hash(self):
        return sha256d(self.serialize())


class Block(Serializable):
    def __init__(self, header, transactions):
        self.header = header
        self.transactions = transactions

    def __getattr__(self, attr):
        """convenience: merge header and summary's attributes into the Block's accessors"""
        if attr in ['version', 'summary', 'pow_evidence', 'hash']:
            return getattr(self.header, attr)

        if attr in ['height', 'previous_block_hash', 'merkle_root_hash', 'timestamp', 'target', 'nonce']:
            return getattr(self.header.summary, attr)

        raise AttributeError("'Block' object has no attribute '%s'" % attr)

    def __repr__(self):
        return "Block #%s" % human(self.header.hash())

    def __eq__(self, other):
        return (
            isinstance(other, Block) and
            self.header == other.header and
            # for valid blocks comparing transactions is superfluous but we don't make that assumption here
            self.transactions == other.transactions
        )

    @classmethod
    def stream_deserialize(cls, f):
        header = BlockHeader.stream_deserialize(f)
        transactions = stream_deserialize_list(f, Transaction)
        return cls(header, transactions)

    def stream_serialize(self, f):
        self.header.stream_serialize(f)
        stream_serialize_list(f, self.transactions)

    def get_total_work(self):
        return self.height  # TODO this is totally a placeholder :-D


__all__ = [
    'OutputReference',
    'Input',
    'Output',
    'Transaction',
    'PowEvidence',
    'BlockSummary',
    'BlockHeader',
    'Block',
]
