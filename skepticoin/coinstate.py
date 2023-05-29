from __future__ import annotations
from collections import deque

from typing import Deque, Dict, List, Optional, Tuple

import immutables
from skepticoin.blockpath import BlockPath

from skepticoin.blockstore import BlockStore

from .datatypes import Output, OutputReference, Block, BlockSummary
from .humans import human


class CoinState:

    def __init__(self, blockstore: BlockStore):

        self.blockstore: BlockStore = blockstore

        self.immutability_fence: int = blockstore.sql("select max(block_id) from chain")[0][0]

        self.current_chain_hash: bytes = blockstore.sql(
            """select block_hash from chain
               where height = (select max(height) from chain)
               order by block_hash limit 1""")[0][0]
        self.head_block: Block = self.blockstore.fetch_block_by_hash(self.current_chain_hash)

        self.heads: immutables.Map[bytes, Block] = immutables.Map(
            {row[0]: self.blockstore.fetch_block(
                row[1]) for row in blockstore.sql(
                """select block_hash, block_id from chain
                where height >= (select max(height) from chain) - 10 and block_hash not in (
                    select previous_block_hash from chain where previous_block_hash is not null
                )""")})

        self.block_hash_index: Dict[bytes, Tuple[int, int]] = {
            row[0]: (row[1], row[2])
            for row in self.blockstore.sql(
                "select block_hash, block_id, previous_block_id from chain where target <> zeroblob(32)")
        }

        self.cached_path: BlockPath = BlockPath([])

    def checkout(self, block_hash: bytes) -> CoinState:
        "Return a new CoinState that is a snapshot of a past state or fork at the given block hash"
        new_state = CoinState.__new__(CoinState)
        new_state.blockstore = self.blockstore.unshare_connection()
        new_state.head_block = self.blockstore.fetch_block_by_hash(block_hash)

        new_state.current_chain_hash = block_hash
        new_state.cached_path = self.get_block_id_path(block_hash)
        new_state.block_hash_index = self.block_hash_index
        new_state.immutability_fence = self.block_hash_index[block_hash][0]

        # assume any code working with a checked-out chain doesn't care about other forks
        new_state.heads = immutables.Map({new_state.current_chain_hash: new_state.head_block})
        return new_state

    def __repr__(self) -> str:
        if self.current_chain_hash is None:
            return "CoinState @ empty"
        return "CoinState @ %s (h. %s) w/ %s heads" % (
            human(self.current_chain_hash), self.head().height, len(self.heads))

    @classmethod
    def empty(cls) -> CoinState:
        class Primordial(CoinState):
            # The state before Genesis. Required, but not very useful.

            def __init__(self) -> None:
                self.current_chain_hash = None  # type: ignore
                self.block_hash_index = {}
                self.heads = immutables.Map()
                self.head_block = None  # type: ignore
                self.immutability_fence = -1

        return Primordial()

    def head(self) -> BlockSummary:
        return self.head_block.header.summary

    def block_by_height_at_head(self, height: int) -> Block:
        return self.block_by_height_by_hash(self.current_chain_hash, height)

    def block_by_height_by_hash(self, head_hash: bytes, height: int) -> Block:
        try:
            path_index = self.get_block_id_path(head_hash)
            return self.blockstore.fetch_block(path_index[height])
        except IndexError:
            raise IndexError("Block not found at height %s for hash=%s in %s" % (
                height, human(head_hash), self))

    def forks(self, depth: int) -> List[Tuple[Block, Block]]:
        block_ids = self.blockstore.sql(
            "select block_id from chain where height > ?", (self.head().height - depth,))
        blocks = [self.blockstore.fetch_block(block_id[0]) for block_id in block_ids]
        block_map = {block.hash(): block for block in blocks}

        def _find_lca(left: Block, right: Block) -> Block:
            if left.height > right.height:
                left = block_map[left.previous_block_hash]
                return _find_lca(left, right)
            elif right.height > left.height:
                right = block_map[right.previous_block_hash]
                return _find_lca(left, right)
            elif left.hash() == right.hash():
                return left
            else:
                left = block_map[left.previous_block_hash]
                right = block_map[right.previous_block_hash]
                return _find_lca(left, right)

        forks = []
        for block in sorted(self.heads.values(), key=lambda block: -block.height):  # type: ignore
            try:
                common_ancestor = _find_lca(block, self.head_block)
                forks.append((block, common_ancestor))
            except KeyError:
                pass

        return forks

    def fork_count(self, depth: int) -> int:
        return len([head for head in self.heads.values() if head.height > self.head().height - depth])

    def add_block_batch(self, blocks: List[Block]) -> CoinState:
        coinstate = self

        i = 0
        while i < len(blocks):
            block = blocks[i]
            if (coinstate.has_block_hash(block.previous_block_hash)
                    or block.height == 0
                    or (i > 0 and blocks[i-1].hash() == block.previous_block_hash)):
                i += 1
            else:
                print(f"discarded {block}")
                del blocks[i]

        block_id = coinstate.blockstore.write_blocks_to_disk(blocks)

        for i, block in enumerate(blocks):
            coinstate = coinstate.add_block_no_validation(block, block_id[i])

        coinstate.blockstore = coinstate.blockstore.unshare_connection()
        return coinstate

    def add_block_no_validation(self, block: Block, block_id: Optional[int]) -> CoinState:

        if block_id is None:  # block already in database, possibly added in another thread
            with self.blockstore.locked_cursor() as cur:
                block_id = cur.execute("select block_id from chain where block_hash = ?",
                                       (block.hash(),)).fetchall()[0][0]

        new_state = CoinState.__new__(CoinState)
        new_state.blockstore = self.blockstore
        new_state.immutability_fence = block_id  # must be monotonically increasing

        if self.current_chain_hash is None or self.current_chain_hash == block.previous_block_hash:
            # base case / simple moving ahead
            new_state.current_chain_hash = block.hash()
            new_state.head_block = block
        # what should be the current_chain_hash in the case of forks?
        # using lowest hash as a tie-breaker (instead of first-come first-serve) helps
        # stop the growth of micro-forks seen when testing with multiple nodes
        elif block.height > self.head_block.height or (
                block.height == self.head_block.height and
                block.hash() < self.head_block.hash()
        ):
            new_state.current_chain_hash = block.hash()
            new_state.head_block = block
        else:
            # a fork, but the most recently added block is non-current
            new_state.current_chain_hash = self.current_chain_hash
            new_state.head_block = self.head_block

        new_state.heads = self.heads.set(block.hash(), block)
        if block.previous_block_hash in new_state.heads:
            new_state.heads = new_state.heads.delete(block.previous_block_hash)

        # skepticoin fails in mysterious ways if "future" blocks become visible to
        # old CoinStates. The contortions below are to ensure this doesn't happen.
        if new_state.immutability_fence > self.immutability_fence:
            # normal case, high performance with low memory consuption
            new_state.block_hash_index = self.block_hash_index
        else:
            # in this case the only way to guarantee immutability is to clone it
            new_state.block_hash_index = self.block_hash_index.copy()
            new_state.immutability_fence = self.immutability_fence

        if self.has_block_hash(block.previous_block_hash):
            previous_block_id = self.block_hash_index[block.previous_block_hash][0]
        else:
            assert block.height == 0
            previous_block_id = -1

        new_state.block_hash_index[block.hash()] = (block_id, previous_block_id)
        new_state.cached_path: List[int] = None  # type: ignore
        return new_state

    def get_block_id_path(self, at_hash: bytes) -> BlockPath:

        if self.cached_path and at_hash == self.current_chain_hash:
            return self.cached_path

        if at_hash == self.head_block.previous_block_hash:
            return self.get_path_to_head().slice(0, -1)

        backward_chains = {t[0]: t[1] for t in self.block_hash_index.copy().values()}
        (next, _) = self.block_hash_index[at_hash]
        chain: Deque[int] = deque()

        while next:
            chain.appendleft(next)
            next = backward_chains[next]

        if not chain:
            raise KeyError("No path found to block hash %s at %s" % (at_hash.hex(), str(self)))

        out = BlockPath(list(chain))

        if at_hash == self.current_chain_hash:
            self.cached_path = out

        return out

    def get_path_to_head(self) -> BlockPath:
        return self.get_block_id_path(self.current_chain_hash)

    def get_block_hashes_at_heights(self, heights: List[int]) -> List[bytes]:

        block_id_path = self.get_path_to_head()
        block_id_at_height = [block_id_path[height] for height in heights]

        query = "SELECT block_hash, block_id FROM chain WHERE block_id IN (%s)" % ','.join(
            ['?'] * len(block_id_at_height))

        rows: List[Tuple[bytes, int]] = self.blockstore.sql(query, block_id_at_height)  # type: ignore
        assert len(heights) == len(rows), f"Expected rows={block_id_at_height}, got: {[str(row[1]) for row in rows]}"

        # reorder the response rows to match the order of the input heights
        id_hash = {row[1]: row[0] for row in rows}
        return [id_hash[block_id_path[height]] for height in heights]

    def has_block_hash(self, block_hash: bytes) -> bool:
        (immutability_epoch, _) = self.block_hash_index.get(block_hash, (None, None))
        if immutability_epoch is None:
            return False
        else:
            # if a block was added to the map later than the fence, it doesn't exist yet
            return immutability_epoch <= self.immutability_fence

    def get_block_by_hash(self, block_hash: bytes) -> Block:
        return self.blockstore.fetch_block_by_hash(block_hash)

    def unspent_transaction_outs_at_head(self, ref: OutputReference) -> Optional[Output]:
        from skepticoin.balances import get_output_if_not_consumed
        return get_output_if_not_consumed(self.blockstore, ref, self.get_path_to_head())
