<<<<<<< HEAD
from __future__ import annotations

from collections import namedtuple
from typing import Any, List, Optional, Tuple

=======
>>>>>>> parent of acb1901... Fix: format all files
import immutables
from collections import namedtuple

<<<<<<< HEAD
from skepticoin.datatypes import (
    Block,
    BlockSummary,
    Output,
    OutputReference,
    Transaction,
)
from skepticoin.genesis import genesis_block_data
from skepticoin.humans import human
from skepticoin.signing import PublicKey
=======
from .datatypes import OutputReference, Block
from .humans import human
from .genesis import genesis_block_data
>>>>>>> parent of acb1901... Fix: format all files


PKBalance = namedtuple('PKBalance', ['value', 'output_references'])


def uto_apply_transaction(
    unspent_transaction_outs: immutables.Map[OutputReference, Output],
    transaction: Transaction,
    is_coinbase: bool,
) -> immutables.Map[OutputReference, Output]:
    with unspent_transaction_outs.mutate() as mutable_unspent_transaction_outs:

        # for coinbase we must skip the input-removal because the input references "thin air" rather than an output.
        if not is_coinbase:
            for input in transaction.inputs:
                # we don't explicitly check that the transaction is spendable; inadvertant violation of that expectation
                # will lead to an application-crash (which is preferable over the alternative: double-spending).
                del mutable_unspent_transaction_outs[input.output_reference]

        for i, output in enumerate(transaction.outputs):
            output_reference = OutputReference(transaction.hash(), i)
            mutable_unspent_transaction_outs[output_reference] = output

        return mutable_unspent_transaction_outs.finish()


<<<<<<< HEAD
def uto_apply_block(
    unspent_transaction_outs: immutables.Map[OutputReference, Output], block: Block
) -> immutables.Map[OutputReference, Output]:
    unspent_transaction_outs = uto_apply_transaction(
        unspent_transaction_outs, block.transactions[0], is_coinbase=True
    )
=======
def uto_apply_block(unspent_transaction_outs, block):
    unspent_transaction_outs = uto_apply_transaction(unspent_transaction_outs, block.transactions[0], is_coinbase=True)
>>>>>>> parent of acb1901... Fix: format all files
    for transaction in block.transactions[1:]:
        unspent_transaction_outs = uto_apply_transaction(unspent_transaction_outs, transaction, is_coinbase=False)
    return unspent_transaction_outs


<<<<<<< HEAD
def pkb_apply_transaction(
    unspent_transaction_outs: immutables.Map[OutputReference, OutputReference],
    public_key_balances: immutables.Map[PublicKey, PKBalance],
    transaction: Transaction,
    is_coinbase: bool,
) -> immutables.Map[PublicKey, PKBalance]:
=======
def pkb_apply_transaction(unspent_transaction_outs, public_key_balances, transaction, is_coinbase):
>>>>>>> parent of acb1901... Fix: format all files
    with public_key_balances.mutate() as mutable_public_key_balances:
        # for coinbase we must skip the input-removal because the input references "thin air" rather than an output.
        if not is_coinbase:
            for input in transaction.inputs:
<<<<<<< HEAD
                previously_unspent_output: Output = unspent_transaction_outs[
                    input.output_reference
                ]
=======
                previously_unspent_output = unspent_transaction_outs[input.output_reference]
>>>>>>> parent of acb1901... Fix: format all files

                public_key = previously_unspent_output.public_key
                mutable_public_key_balances[public_key] = PKBalance(
                    mutable_public_key_balances[public_key].value - previously_unspent_output.value,
                    [to for to in mutable_public_key_balances[public_key].output_references
                     if to != input.output_reference]
                )

        for i, output in enumerate(transaction.outputs):
            output_reference = OutputReference(transaction.hash(), i)

            if output.public_key not in mutable_public_key_balances:
                mutable_public_key_balances[output.public_key] = PKBalance(0, [])

            mutable_public_key_balances[output.public_key] = PKBalance(
                mutable_public_key_balances[output.public_key].value + output.value,
                mutable_public_key_balances[output.public_key].output_references + [output_reference],
            )

        return mutable_public_key_balances.finish()


def pkb_apply_block(
    unspent_transaction_outs: immutables.Map[OutputReference, OutputReference],
    public_key_balances: immutables.Map[PublicKey, PKBalance],
    block: Block,
) -> immutables.Map[PublicKey, PKBalance]:
    # unspent_transaction_outs is used as a "reference" only (for looking up outputs); note that we never have to update
    # that reference inside this function, because intra-block spending is invalid per the consensus.

    public_key_balances = pkb_apply_transaction(
        unspent_transaction_outs, public_key_balances, block.transactions[0], is_coinbase=True)

    for transaction in block.transactions[1:]:
        public_key_balances = pkb_apply_transaction(unspent_transaction_outs, public_key_balances, transaction, False)

    return public_key_balances


class CoinState:
<<<<<<< HEAD
    def __init__(
        self,
        block_by_hash: immutables.Map[bytes, BlockSummary],
        unspent_transaction_outs_by_hash: immutables.Map[
            bytes, immutables.Map[OutputReference, Output]
        ],
        block_by_height_by_hash: immutables.Map[bytes, immutables.Map[int, Block]],
        heads: immutables.Map[bytes, Block],
        current_chain_hash: Optional[bytes],
        public_key_balances_by_hash: immutables.Map[
            bytes, immutables.Map[PublicKey, PKBalance]
        ],
    ):
=======
    def __init__(self, block_by_hash, unspent_transaction_outs_by_hash, block_by_height_by_hash, heads,
                 current_chain_hash, public_key_balances_by_hash):
>>>>>>> parent of acb1901... Fix: format all files

        self.block_by_hash = block_by_hash

        # block_hash -> (OutputReference -> Output)
        self.unspent_transaction_outs_by_hash = unspent_transaction_outs_by_hash

        # given a hash to a current head, return a dictionary in which you can look up by height.
        self.block_by_height_by_hash = block_by_height_by_hash

        self.heads = heads  # hash=>block ... but restricted to blocks w/o children.
        self.current_chain_hash = current_chain_hash

        # block_hash -> (public_key -> (value, [OutputReference]))
        self.public_key_balances_by_hash = public_key_balances_by_hash

    def __repr__(self) -> str:
        if self.current_chain_hash is None:
            return "CoinState @ empty"
        return "CoinState @ %s (h. %s) w/ %s heads" % (
            human(self.current_chain_hash), self.head().height, len(self.heads))

    @classmethod
    def empty(cls) -> CoinState:
        return cls(
            block_by_hash=immutables.Map(),
            unspent_transaction_outs_by_hash=immutables.Map(),
            block_by_height_by_hash=immutables.Map(),
            heads=immutables.Map(),
            current_chain_hash=None,
            public_key_balances_by_hash=immutables.Map(),
        )

    @classmethod
    def zero(cls) -> CoinState:
        e = cls.empty()
        return e.add_block_no_validation(Block.deserialize(genesis_block_data))

<<<<<<< HEAD
    def add_block(self, block: Block, current_timestamp: int) -> CoinState:
        from skepticoin.consensus import (
            validate_block_by_itself,
            validate_block_in_coinstate,
        )

=======
    def add_block(self, block, current_timestamp):
        from skepticoin.consensus import validate_block_by_itself, validate_block_in_coinstate
>>>>>>> parent of acb1901... Fix: format all files
        validate_block_by_itself(block, current_timestamp)
        validate_block_in_coinstate(block, self)

        return self.add_block_no_validation(block)

<<<<<<< HEAD
    def add_block_no_validation(self, block: Block) -> CoinState:
        if block.previous_block_hash == b"\00" * 32:
=======
    def add_block_no_validation(self, block):
        if block.previous_block_hash == b'\00' * 32:
>>>>>>> parent of acb1901... Fix: format all files
            unspent_transaction_outs = immutables.Map()
            public_key_balances = immutables.Map()
        else:
            unspent_transaction_outs = self.unspent_transaction_outs_by_hash[block.previous_block_hash]
            public_key_balances = self.public_key_balances_by_hash[block.previous_block_hash]

        public_key_balances = pkb_apply_block(unspent_transaction_outs, public_key_balances, block)
        # NOTE: ordering matters b/c we assign to unspent_transaction_outs; perhaps just distinguish?
        unspent_transaction_outs = uto_apply_block(unspent_transaction_outs, block)

        block_by_hash = self.block_by_hash.set(block.hash(), block)

        # TODO pruning of unspent_transaction_outs_by_hash on e.g. max delta-height; because it is used as part of
        # validation, such an approach implies a limit (to be implemented in validation) on how old a fork may be w.r.t.
        # the current height if it is to be considered at all.
        unspent_transaction_outs_by_hash = self.unspent_transaction_outs_by_hash.set(
            block.hash(), unspent_transaction_outs)

        public_key_balances_by_hash = self.public_key_balances_by_hash.set(
            block.hash(), public_key_balances)

        if block.previous_block_hash == b'\00' * 32:
            block_by_height_by_hash = immutables.Map({block.hash(): immutables.Map({0: block})})
        else:
            block_by_height = self.block_by_height_by_hash[block.previous_block_hash]
            block_by_height = block_by_height.set(block.height, block)
            block_by_height_by_hash = self.block_by_height_by_hash.set(block.hash(), block_by_height)

        with self.heads.mutate() as mutable_heads:
            if block.previous_block_hash in mutable_heads:
                del mutable_heads[block.header.summary.previous_block_hash]

            mutable_heads[block.hash()] = block

            heads = mutable_heads.finish()

        if self.current_chain_hash is None or self.current_chain_hash == block.previous_block_hash:
            # base case / simple moving ahead
            current_chain_hash = block.hash()

        # what should be the current_chain_hash in the case of forks?
        # we compare total work, using striclty greater: this means that when there is a fork in the chain, ties are
        # broken based on first-come-first serve. I'm sure someone wrote a paper on how this is optimal.
        elif block.get_total_work() > self.block_by_hash[self.current_chain_hash].get_total_work():
            current_chain_hash = block.hash()
        else:
            current_chain_hash = self.current_chain_hash  # a fork, but the most recently added block is non-current

        return CoinState(
            block_by_hash=block_by_hash,
            unspent_transaction_outs_by_hash=unspent_transaction_outs_by_hash,
            block_by_height_by_hash=block_by_height_by_hash,
            heads=heads,
            current_chain_hash=current_chain_hash,
            public_key_balances_by_hash=public_key_balances_by_hash,
        )

    def head(self) -> BlockSummary:
        return self.block_by_hash[self.current_chain_hash]  # type: ignore

    def by_height_at_head(self) -> immutables.Map[int, Block]:
        # TODO just use 'at_head'
        return self.block_by_height_by_hash[self.current_chain_hash]

    @property
<<<<<<< HEAD
    def at_head(self) -> Any:  # TODO refactor, mypy doesn't like property classes
=======
    def at_head(self):

>>>>>>> parent of acb1901... Fix: format all files
        class AtHead:
            @property
            def unspent_transaction_outs(
                inner_self,
            ) -> immutables.Map[OutputReference, Output]:
                return self.unspent_transaction_outs_by_hash[self.current_chain_hash]

            @property
            def block_by_height(inner_self) -> immutables.Map[int, Block]:
                return self.block_by_height_by_hash[self.current_chain_hash]

            @property
            def public_key_balances(inner_self) -> immutables.Map[PublicKey, PKBalance]:
                return self.public_key_balances_by_hash[self.current_chain_hash]

        return AtHead()

    def forks(self) -> List[Tuple[Block, Block]]:
        def _find_lca_with_main(block: Block) -> Block:
            # while block.hash() not in block_by_hash_by_hash  ... we have no such datastructure yet, so instead:

            while (block.height not in self.by_height_at_head() or
                    self.by_height_at_head()[block.height].hash() != block.hash()):

                block = self.block_by_hash[block.previous_block_hash]

            return block

        return [(head, _find_lca_with_main(head)) for head in self.heads.values()]
