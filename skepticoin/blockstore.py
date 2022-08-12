from itertools import groupby
import os
import sqlite3
import threading
from typing import Dict, Iterator, List, Optional

from skepticoin.datatypes import Block, BlockHeader, BlockSummary, Input, Output, OutputReference, PowEvidence, Transaction  # noqa: E501
from skepticoin.hash import sha256d
from skepticoin.signing import PublicKey, Signature
from .genesis import genesis_block_data


def nullify_zeros(value: bytes) -> Optional[bytes]:
    return value if value != b'\00' * 32 else None


def zeroify_nulls(value: Optional[bytes]) -> bytes:
    return value if value else b'\00' * 32


class TransactionBuilder:

    def __init__(self, block_hash: bytes) -> None:
        self.block_hash = block_hash
        self.inputs: Dict[int, Input] = {}
        self.outputs: Dict[int, Output] = {}


class BlockStore:

    def __init__(self, path: str) -> None:

        self.lock = threading.Lock()

        is_memory: bool = path == ":memory:"
        self.is_new: bool = is_memory or not os.path.isfile(path)

        self.connection = sqlite3.connect(path, check_same_thread=False)
        self.sql = self.connection.execute

        self.sql("PRAGMA foreign_keys = ON")
        self.sql("PRAGMA journal_mode = MEMORY")
        self.sql("PRAGMA synchronous = OFF")
        self.sql("PRAGMA page_size = 65536")
        self.sql("PRAGMA cache_size = 10000")

        if self.is_new and not is_memory:
            print("Creating new block database: " + path)
        elif not is_memory:
            print("Reading blocks from " + path)

        if self.is_new:

            self.sql('''CREATE TABLE chain (
                block_hash blob primary key,
                version int,
                height int,
                previous_block_hash blob REFERENCES chain(block_hash),
                merkle_root_hash blob,
                timestamp int,
                target blob,
                nonce int,
                pow_summary_hash blob,
                pow_chain_sample blob,
                pow_block_hash blob
            )''')
            self.sql('''CREATE TABLE transaction_locator (
                transaction_hash blob primary key,
                block_hash blob REFERENCES chain(block_hash)
            )''')
            self.sql('''CREATE TABLE transaction_inputs (
                transaction_hash blob REFERENCES transaction_locator(transaction_hash),
                seq int,
                output_reference_hash blob,
                output_reference_index int,
                signature blob null,
                PRIMARY KEY(transaction_hash, seq),
                FOREIGN KEY(output_reference_hash, output_reference_index)
                REFERENCES transaction_outputs(transaction_hash, seq)
            )''')
            self.sql('''CREATE TABLE transaction_outputs (
                transaction_hash blob REFERENCES transaction_locator(transaction_hash),
                seq int,
                value int,
                public_key blob,
                PRIMARY KEY(transaction_hash, seq)
            )''')
            self.sql('CREATE INDEX chainlink_index ON chain(height, block_hash, previous_block_hash)')
            self.sql('CREATE INDEX previous_block_hash ON chain(previous_block_hash)')
            self.sql('CREATE INDEX tr_locator_block_hash ON transaction_locator(block_hash)')

            self.write_blocks_to_disk([Block.deserialize(genesis_block_data)])

        self.path = path
        self.write_buffer: List[Block] = []

    def add_block_to_buffer(self, block: Block) -> None:
        with self.lock:
            self.write_buffer.append(block)

    def close(self) -> None:
        self.connection.close()
        self.connection = None  # type: ignore

    def write_blocks_to_disk(self, blocks: List[Block]) -> None:

        blocks_param = []
        transactions_param = []
        transaction_inputs_param = []
        transaction_outputs_param = []

        for block in blocks:
            block_hash = block.hash()
            for transaction in block.transactions:
                transaction_bytes = transaction.serialize()
                transaction_hash = sha256d(transaction_bytes)
                transactions_param.append((
                    transaction_hash,
                    block_hash
                ))
                for seq, input in enumerate(transaction.inputs):
                    transaction_inputs_param.append((
                        transaction_hash,
                        seq,
                        nullify_zeros(input.output_reference.hash),
                        input.output_reference.index,
                        input.signature.serialize() if input.signature else None
                    ))
                for seq, output in enumerate(transaction.outputs):
                    transaction_outputs_param.append((
                        transaction_hash,
                        seq,
                        output.value,
                        output.public_key.serialize()
                    ))
            blocks_param.append((
                block_hash,
                block.header.version,
                block.header.summary.height,
                nullify_zeros(block.header.summary.previous_block_hash),
                block.header.summary.merkle_root_hash,
                block.header.summary.timestamp,
                block.header.summary.target,
                block.header.summary.nonce,
                block.header.pow_evidence.summary_hash,
                block.header.pow_evidence.chain_sample,
                block.header.pow_evidence.block_hash
            ))

        cur = self.connection.cursor()
        cur.execute('BEGIN TRANSACTION')
        cur.executemany("insert or ignore into chain values (?,?,?,?,?,?,?,?,?,?,?)", blocks_param)
        cur.executemany("insert or ignore into transaction_locator values (?,?)", transactions_param)
        cur.executemany("insert or ignore into transaction_outputs values (?,?,?,?)", transaction_outputs_param)
        cur.executemany("insert or ignore into transaction_inputs values (?,?,?,?,?)", transaction_inputs_param)
        cur.execute('COMMIT')
        cur.close()

    def flush_blocks_to_disk(self) -> None:
        with self.lock:
            if (len(self.write_buffer)):
                self.write_blocks_to_disk(self.write_buffer)
                self.write_buffer.clear()

    def load_transaction_builders(self) -> Dict[bytes, TransactionBuilder]:
        return {
            row[0]: TransactionBuilder(row[1]) for row in self.sql(
                "select transaction_hash, block_hash from transaction_locator"
            )
        }

    def load_inputs(self, transaction_builders: Dict[bytes, TransactionBuilder]) -> None:
        for row in self.sql("""
                    select output_reference_hash, output_reference_index, signature, transaction_hash, seq
                    from transaction_inputs"""):
            (output_reference_hash, output_reference_index, signature, transaction_hash, seq) = row
            transaction_builders[transaction_hash].inputs[seq] = Input(
                    OutputReference(zeroify_nulls(output_reference_hash), output_reference_index),
                    Signature.deserialize(signature) if signature else None
            )

    def load_outputs(self, transaction_builders: Dict[bytes, TransactionBuilder]) -> None:
        for row in self.sql("select value, public_key, transaction_hash, seq from transaction_outputs"):
            (value, public_key, transaction_hash, seq) = row
            transaction_builders[transaction_hash].outputs[seq] = Output(value, PublicKey.deserialize(public_key))

    def read_blocks_from_disk(self) -> Iterator[Block]:

        transaction_builders = self.load_transaction_builders()

        self.load_inputs(transaction_builders)

        self.load_outputs(transaction_builders)

        block_builders = {
            block_hash: list(builder_tuples)
            for block_hash, builder_tuples
            in groupby(transaction_builders.items(), lambda item: item[1].block_hash)
        }

        for row in self.sql(
                """select height, previous_block_hash, merkle_root_hash, timestamp, target, nonce,
                   pow_summary_hash, pow_chain_sample, pow_block_hash, block_hash
                   from chain order by height"""):
            (height, previous_block_hash, merkle_root_hash, timestamp, target, nonce,
             pow_summary_hash, pow_chain_sample, pow_block_hash, block_hash) = row

            yield Block(
                    BlockHeader(
                        BlockSummary(
                            height=height,
                            previous_block_hash=zeroify_nulls(previous_block_hash),
                            merkle_root_hash=merkle_root_hash,
                            timestamp=timestamp,
                            target=target,
                            nonce=nonce
                        ),
                        PowEvidence(
                            summary_hash=pow_summary_hash,
                            chain_sample=pow_chain_sample,
                            block_hash=pow_block_hash
                        )
                    ),
                    [Transaction(
                        [v for k, v in sorted(builder.inputs.items(), key=lambda i: i[0])],
                        [v for k, v in sorted(builder.outputs.items(), key=lambda i: i[0])],
                        transaction_hash
                    ) for transaction_hash, builder in block_builders[block_hash]],
                    hash=block_hash
            )


class DefaultBlockStore:
    instance = BlockStore('chain.db')
