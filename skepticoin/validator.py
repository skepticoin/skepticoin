from queue import Empty, Queue
from threading import Thread
from time import time
from typing import Optional

from skepticoin.networking.manager import ChainManager
from skepticoin.coinstate import CoinState
from skepticoin.consensus import validate_block_by_itself, validate_block_in_coinstate
from skepticoin.humans import human


class Validator:

    def __init__(self) -> None:
        self.buffer: Queue[int] = Queue()
        self.coinstate: Optional[CoinState] = None
        self.thread: Optional[Thread] = None

    def step(self, chain_manager: ChainManager, same_thread: bool = False) -> None:

        if self.thread is not None:
            return

        if (self.buffer.empty() and
                (self.coinstate is None
                 or self.coinstate.head().height < chain_manager.coinstate.head().height)):

            blockstore = chain_manager.coinstate.blockstore.unshare_connection()

            next_id = blockstore.sql(
                "select coalesce(max(block_id),1) from validation_tracker")[0][0]

            rows = blockstore.sql("select block_id from chain where block_id > ? limit 200", (next_id,))

            for row in rows:
                self.buffer.put(row[0])

            if same_thread:
                self.run(chain_manager)
            else:
                self.thread = Thread(target=self.run, args=(chain_manager,), daemon=True)
                assert self.thread
                self.thread.start()

    def join(self) -> None:
        if self.thread is not None:
            self.thread.join()
            self.thread = None

    def run(self, chain_manager: ChainManager) -> None:

        while True:

            try:
                block_id = self.buffer.get_nowait()
            except Empty:
                self.thread = None
                break

            block = chain_manager.coinstate.blockstore.fetch_block(block_id)

            try:

                if self.coinstate is None or (self.coinstate.current_chain_hash != block.previous_block_hash):
                    self.coinstate = chain_manager.coinstate.checkout(block.previous_block_hash)

                if block.target == b'\00'*32:
                    raise Exception("Block was already invalidated (target=0).")

                if (block.previous_block_hash == self.coinstate.head_block.hash()
                        and self.coinstate.head_block.target == b'\00'*32):
                    raise Exception("This block descends from an invalid block.")

                validate_block_by_itself(block, int(time()))

                # full validation including super-slow POW validation with scrypt()
                validate_block_in_coinstate(block, self.coinstate)

            except Exception as e:
                print("Invalid block at h. %d, hash=%s, error: %s" % (
                        block.height, human(block.hash()), str(e)))

                # deleting the invalid block from the database would cause some new problems,
                # so instead we set target/height to 0, making it impossible to mine further.
                # also nuke any descendents already in the database
                self.coinstate = chain_manager.coinstate
                self.coinstate.blockstore.update("""
                    WITH RECURSIVE descendents(block_hash, previous_block_hash) AS (
                        SELECT block_hash, previous_block_hash
                        FROM chain WHERE block_hash = ?
                        UNION ALL
                        SELECT chain.block_hash, chain.previous_block_hash
                        FROM chain
                        JOIN descendents ON chain.previous_block_hash = descendents.block_hash
                    )
                    UPDATE chain SET target = ?, height = 0 WHERE block_hash IN (
                        SELECT block_hash FROM descendents)""", (block.hash(), b'\00'*32,))  # type: ignore

                # if the blast reached the current chain head, reattach it to another fork
                head = self.coinstate.blockstore.fetch_block_by_hash(self.coinstate.current_chain_hash)

                if head.target == b'\00'*32:
                    print("Invalidating current chain at %s" % self.coinstate)
                    reconstructed_chain = CoinState(self.coinstate.blockstore)
                    chain_manager.set_coinstate(reconstructed_chain)
                    print("Reattached to longest valid fork at %s" % reconstructed_chain)

            else:
                self.coinstate = self.coinstate.add_block_batch([block])

            self.coinstate.blockstore.update(
                "replace into validation_tracker (one,block_id) values (1,?)", (block_id,))
