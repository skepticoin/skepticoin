import os
import sqlite3
import threading
from typing import Any, Dict, List, Optional, Tuple

from skepticoin.datatypes import Block, BlockHeader, BlockSummary, Input, Output, OutputReference, PowEvidence, Transaction  # noqa: E501
from skepticoin.hash import sha256d
from skepticoin.humans import human
from skepticoin.signing import PublicKey, Signature
from .genesis import genesis_block_data

from typing import TypeVar, ContextManager

T = TypeVar('T', bound='BlockStore')


def nullify_zeros(value: bytes) -> Optional[bytes]:
    return value if value != b'\00' * 32 else None


def zeroify_nulls(value: Optional[bytes]) -> bytes:
    return value if value else b'\00' * 32


class BlockStore:

    def __init__(self, path: str) -> None:

        self.lock = threading.Lock()
        self.path = path

        is_memory: bool = path == ":memory:"
        is_new: bool = is_memory or not os.path.isfile(path)

        if is_new and not is_memory:
            print("Creating new block database: " + path)
            conn = sqlite3.connect(path)
            cur = conn.cursor()
            cur.execute("PRAGMA journal_mode = WAL").fetchall()
            cur.execute("PRAGMA page_size = 4096").fetchall()
            conn.close()
        elif not is_memory:
            print("Using existing database: " + path)

        if is_new:

            self.update('''CREATE TABLE chain (
                block_id INTEGER PRIMARY KEY AUTOINCREMENT,
                block_hash blob UNIQUE,
                version int,
                height int,
                previous_block_id INTEGER REFERENCES chain(block_id),
                previous_block_hash blob REFERENCES chain(block_hash),
                merkle_root_hash blob,
                timestamp int,
                target blob,
                nonce int,
                pow_summary_hash blob,
                pow_chain_sample blob,
                pow_block_hash blob
            )''')
            self.update('''CREATE TABLE transaction_locator (
                transaction_hash blob,
                block_hash blob REFERENCES chain(block_hash),
                transaction_seq int,
                PRIMARY KEY(block_hash, transaction_seq)
            )''')
            self.update('''CREATE TABLE transaction_inputs (
                transaction_hash blob,
                seq int,
                output_reference_hash blob,
                output_reference_index int,
                signature blob null,
                PRIMARY KEY(transaction_hash, seq),
                FOREIGN KEY(output_reference_hash, output_reference_index)
                REFERENCES transaction_outputs(transaction_hash, seq)
            )''')
            self.update('''CREATE TABLE transaction_outputs (
                transaction_hash blob,
                seq int,
                value int,
                public_key blob,
                PRIMARY KEY(transaction_hash, seq)
            )''')
            self.update('CREATE INDEX chain_index ON chain(height, block_id, previous_block_id)')
            self.update('CREATE INDEX id_hash_index ON chain(block_id, block_hash)')
            self.update('CREATE INDEX previous_block_hash ON chain(previous_block_hash)')
            self.update('CREATE INDEX tx_hash ON transaction_locator(transaction_hash)')

            self.update('''CREATE INDEX transaction_output_public_keys
                        ON transaction_outputs(public_key)''')

            self.update('''CREATE INDEX transaction_inputs_output_reference
                        ON transaction_inputs(output_reference_hash, output_reference_index)''')

            self.update('''CREATE TABLE validation_tracker
                        (one INTEGER PRIMARY KEY, block_id INTEGER)''')

        if is_new:
            self.write_blocks_to_disk([Block.deserialize(genesis_block_data)])

        self.reader_connection = sqlite3.connect(self.path, check_same_thread=False)

    def unshare_connection(self) -> 'BlockStore':
        # enable sharing between multiple threads (sqlite is weird)
        clone = BlockStore.__new__(BlockStore)
        clone.reader_connection = sqlite3.connect(self.path, check_same_thread=False)
        clone.lock = threading.Lock()
        clone.path = self.path
        return clone

    def locked_cursor(self) -> ContextManager[sqlite3.Cursor]:

        class LockedCursorContext:
            def __init__(self, blockstore: BlockStore) -> None:
                self.blockstore = blockstore

            def __enter__(self) -> sqlite3.Cursor:
                self.blockstore.lock.acquire()
                self.connection: sqlite3.Connection = sqlite3.connect(self.blockstore.path, check_same_thread=True)
                self.cursor = self.connection.cursor()
                return self.cursor

            def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
                if self.cursor is not None:
                    self.cursor.close()
                if self.connection is not None:
                    self.connection.close()
                self.blockstore.lock.release()

        return LockedCursorContext(self)

    def sql(self, query: str, *args: Tuple[Any]) -> List[List[Any]]:
        cur = self.reader_connection.cursor()
        rows = cur.execute(query, *args).fetchall()
        cur.close()
        return rows

    def explain(self, query: str, *args: Tuple[Any]) -> List[List[Any]]:
        with self.locked_cursor() as cur:
            for row in cur.execute(f"EXPLAIN QUERY PLAN {query}", *args):
                print(row)
        with self.locked_cursor() as cur:
            rows = cur.execute(query, *args).fetchall()
            return rows

    def write_blocks_to_disk(self, blocks: List[Block]) -> List[Optional[int]]:

        block_id: List[Optional[int]] = []

        with self.locked_cursor() as cur:

            cur.execute("PRAGMA foreign_keys = ON")
            cur.execute("PRAGMA synchronous = NORMAL")
            cur.execute('BEGIN TRANSACTION')

            transactions_param = []
            transaction_inputs_param = []
            transaction_outputs_param = []

            for block in blocks:

                block_hash = block.hash()
                for transaction_seq, transaction in enumerate(block.transactions):
                    transaction_bytes = transaction.serialize()
                    transaction_hash = sha256d(transaction_bytes)
                    transactions_param.append((
                        transaction_hash,
                        block_hash,
                        transaction_seq
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
                blocks_param = [
                    block_hash,
                    block.header.version,
                    block.header.summary.height,
                    nullify_zeros(block.header.summary.previous_block_hash),
                    nullify_zeros(block.header.summary.previous_block_hash),
                    block.header.summary.merkle_root_hash,
                    block.header.summary.timestamp,
                    block.header.summary.target,
                    block.header.summary.nonce,
                    block.header.pow_evidence.summary_hash,
                    block.header.pow_evidence.chain_sample,
                    block.header.pow_evidence.block_hash
                ]

                cur.execute("""
                    insert or ignore into chain values (
                        NULL,?,?,?,(
                            select block_id from chain where block_hash = ?
                        ), ?,?,?,?,?,?,?,?)""", blocks_param)

                block_id.append(cur.lastrowid if cur.lastrowid != 0 else None)

            cur.executemany(
                "insert or ignore into transaction_locator values (?,?,?)",
                transactions_param).fetchall()

            cur.executemany(
                "insert or ignore into transaction_outputs values (?,?,?,?)",
                transaction_outputs_param).fetchall()

            cur.executemany(
                "insert or ignore into transaction_inputs values (?,?,?,?,?)",
                transaction_inputs_param).fetchall()

            cur.execute('COMMIT')

        return block_id

    def fetch_block(self, block_id: int) -> Block:

        cur = self.reader_connection.cursor()

        row = cur.execute(
                """select height, previous_block_hash, merkle_root_hash, timestamp, target, nonce,
                pow_summary_hash, pow_chain_sample, pow_block_hash, block_hash
                from chain where block_id = ?""", (block_id,)).fetchone()

        if not row:
            raise Exception("Block not found at block_id: " + str(block_id))

        (height, previous_block_hash, merkle_root_hash, timestamp, target, nonce,
            pow_summary_hash, pow_chain_sample, pow_block_hash, block_hash) = row

        transaction_builder: Dict[bytes, Tuple[Dict[int, Input], Dict[int, Output]]] = {}

        # Transactions must be read back in the same order they were written to sqlite.
        # This was not a deliberate design decision, it just happened to work as coded.
        transaction_order = [row[0] for row in cur.execute(
            "select transaction_hash from transaction_locator where block_hash = ?",
            (block_hash,)).fetchall()]

        for row in cur.execute("""
            select output_reference_hash, output_reference_index, signature, transaction_hash, seq
                from transaction_inputs
                where transaction_hash in (%s)""" % (
                    ','.join(['?'] * len(transaction_order))),
                    transaction_order):

            (output_reference_hash, output_reference_index, signature, transaction_hash, seq) = row

            transaction_builder.setdefault(transaction_hash, ({}, {}))
            transaction_builder[transaction_hash][0][seq] = Input(
                    OutputReference(zeroify_nulls(output_reference_hash), output_reference_index),
                    Signature.deserialize(signature) if signature else None
            )

        for row in cur.execute("""
                select value, public_key, transaction_hash, seq
                from transaction_outputs
                where transaction_hash in (%s)""" % (
                    ','.join(['?'] * len(transaction_order)),
                ), transaction_order):
            (value, public_key, transaction_hash, seq) = row
            transaction_builder.setdefault(transaction_hash, ({}, {}))
            transaction_builder[transaction_hash][1][seq] = Output(value, PublicKey.deserialize(public_key))

        cur.close()

        transactions = [Transaction(
                [v for k, v in sorted(
                    transaction_builder[transaction_hash][0].items(), key=lambda i: i[0])],
                [v for k, v in sorted(
                    transaction_builder[transaction_hash][1].items(), key=lambda i: i[0])],
                transaction_hash
            ) for transaction_hash in transaction_order]

        return Block(
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
                transactions,
                hash=block_hash
        )

    def fetch_block_by_hash(self, block_hash: bytes) -> Block:

        rows = self.sql("select block_id from chain where block_hash = ?",
                        (block_hash,))

        if not rows:
            raise KeyError('Block Hash Not Found: ' + human(block_hash))

        return self.fetch_block(rows[0][0])

    def update(self, query: str, *args: Tuple[Any]) -> None:
        with self.locked_cursor() as cur:
            cur.execute("BEGIN TRANSACTION").fetchall()
            cur.execute(query, *args).fetchall()
            cur.execute("COMMIT").fetchall()

    def validation_queue_size(self) -> int:
        result = self.sql("""
            select count(*) from chain where block_id >
                   (select block_id from validation_tracker limit 1)
        """)
        return result[0][0] if result else 0  # type: ignore
