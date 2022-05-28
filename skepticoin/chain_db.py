
import io
import os
from pathlib import Path
import pickle
import sqlite3
from skepticoin.coinstate import CoinState
from skepticoin.datatypes import Block, BlockHeader, BlockSummary, PowEvidence, Transaction
from skepticoin.humans import computer, human

from skepticoin.serialization import stream_deserialize_list, stream_serialize_list


class BlockChainDatabase:

    def __init__(self, path: str) -> None:
        if not os.path.isfile(path):
            print("Creating new database: " + path)
            con = sqlite3.connect(path)
            cur = con.cursor()
            cur.execute('''CREATE TABLE chain (
                hash blob primary key,
                version int,
                height int,
                previous_block_hash blob,
                merkle_root_hash blob,
                timestamp int,
                target blob,
                nonce int,
                summary_hash blob,
                chain_sample blob,
                block_hash blob,
                transactions blob
            )''')
            con.close()

        self.connection = sqlite3.connect(path, check_same_thread=False)
        self.path = path

    def close(self) -> None:
        self.connection.close()
        self.connection = None  # type: ignore

    def write_block_to_disk(self, block: Block, commit: bool = True) -> None:
        with io.BytesIO() as buffer:
            stream_serialize_list(buffer, block.transactions)
            buffer.seek(0)
            transactions = buffer.read()
        cur = self.connection.cursor()
        cur.execute("insert or ignore into chain values (?,?,?,?,?,?,?,?,?,?,?,?)", (
            block.hash(),
            block.header.version,
            block.header.summary.height,
            block.header.summary.previous_block_hash,
            block.header.summary.merkle_root_hash,
            block.header.summary.timestamp,
            block.header.summary.target,
            block.header.summary.nonce,
            block.header.pow_evidence.summary_hash,
            block.header.pow_evidence.chain_sample,
            block.header.pow_evidence.block_hash,
            transactions
        ))
        cur.close()
        if commit:
            self.connection.commit()

    def write_chain_to_disk(self, coinstate: CoinState) -> None:

        try:
            for hash in coinstate.block_by_hash.keys():
                block = coinstate.block_by_hash[hash]
                self.write_block_to_disk(block, commit=False)
            self.connection.commit()

        except Exception as e:
            print('Failed to save blockchain to disk: ' + str(e))
            return

    def read_chain_from_disk(self) -> CoinState:

        rewrite = False

        if os.path.isfile(self.path):
            print("Reading chain database")
            con = sqlite3.connect(self.path)
            cur = con.cursor()
            block_by_hash = {}
            for row in cur.execute("""select
                    height, previous_block_hash, merkle_root_hash, timestamp, target, nonce,
                    summary_hash, chain_sample, block_hash,
                    transactions
                    from chain"""):
                summary = BlockSummary(height=row[0],
                                       previous_block_hash=row[1],
                                       merkle_root_hash=row[2],
                                       timestamp=row[3],
                                       target=row[4],
                                       nonce=row[5])
                pow_evidence = PowEvidence(summary_hash=row[6],
                                           chain_sample=row[7],
                                           block_hash=row[8])
                header = BlockHeader(summary, pow_evidence)
                transactions = stream_deserialize_list(io.BytesIO(row[9]), Transaction)
                block = Block(header, transactions)
                block_by_hash[block.hash()] = block

            coinstate = CoinState.load(lambda: block_by_hash)
            con.close()

        elif os.path.isfile('chain.cache'):
            print("Reading cached chain in legacy format")
            with open('chain.cache', 'rb') as file:
                coinstate = CoinState.load(lambda: pickle.load(file))
            rewrite = True
        else:
            coinstate = CoinState.zero()

        if os.path.isdir('chain'):
            # the code below is no longer needed by normal users, but some old testcases still rely on it:
            for filename in sorted(os.listdir('chain')):
                (height_str, hash_str) = filename.split("-")
                (height, hash) = (int(height_str), computer(hash_str))

                if hash not in coinstate.block_by_hash:

                    if height % 1000 == 0:
                        print(filename)

                    if os.path.getsize(f"chain/{filename}") == 0:
                        print("Stopping at empty block file: %s" % filename)
                        break

                    with open(Path("chain") / filename, 'rb') as f:
                        try:
                            block = Block.stream_deserialize(f)
                        except Exception as e:
                            raise Exception("Corrupted block on disk: %s" % filename) from e
                        try:
                            coinstate = coinstate.add_block_no_validation(block)
                        except Exception:
                            print("Failed to add block at height=%d, previous_hash=%s"
                                  % (block.height, human(block.header.summary.previous_block_hash)))
                            break

                    rewrite = True

        if rewrite:
            print("Rewriting chain in database format")
            self.write_chain_to_disk(coinstate)
            # cleanup some old files
            if os.path.isfile('chain.cache'):
                print("Deleting old legacy chain.cache file")
                os.remove('chain.cache')
            if os.path.isfile('chain.cache.tmp'):
                print("Deleting old temporary chain.cache.tmp file")
                os.remove('chain.cache.tmp')

        return coinstate


class DefaultDatabase:
    instance = BlockChainDatabase('chain.db')
