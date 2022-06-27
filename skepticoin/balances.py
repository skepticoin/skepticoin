from collections import namedtuple
from typing import Dict, Iterator, List, Optional
import immutables

from skepticoin.datatypes import Block, Output, OutputReference, Transaction
from skepticoin.signing import PublicKey


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


def uto_apply_block(
    unspent_transaction_outs: immutables.Map[OutputReference, Output], block: Block
) -> immutables.Map[OutputReference, Output]:
    unspent_transaction_outs = uto_apply_transaction(unspent_transaction_outs, block.transactions[0], is_coinbase=True)
    for transaction in block.transactions[1:]:
        unspent_transaction_outs = uto_apply_transaction(unspent_transaction_outs, transaction, is_coinbase=False)
    return unspent_transaction_outs


def pkb_apply_transaction(
    unspent_transaction_outs: immutables.Map[OutputReference, Output],
    public_key_balances: immutables.Map[PublicKey, PKBalance],
    transaction: Transaction,
    is_coinbase: bool,
) -> immutables.Map[PublicKey, PKBalance]:
    with public_key_balances.mutate() as mutable_public_key_balances:
        # for coinbase we must skip the input-removal because the input references "thin air" rather than an output.
        if not is_coinbase:
            for input in transaction.inputs:
                previously_unspent_output = unspent_transaction_outs[input.output_reference]

                public_key: PublicKey = previously_unspent_output.public_key
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
    unspent_transaction_outs: immutables.Map[OutputReference, Output],
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


class PublicKeyBalances():

    def __init__(
        self,
        block_by_hash: immutables.Map[bytes, Block],
    ) -> None:

        self.block_by_hash = block_by_hash
        self.cache: Dict[bytes, immutables.Map[PublicKey, PKBalance]] = {}

    def chain_at_hash(self, hash: bytes) -> Iterator[Block]:
        block = self.block_by_hash[hash]
        reverse_chain: List[Block] = [block]
        while block.previous_block_hash != b'\x00' * 32:
            previous_hash = block.previous_block_hash
            block = self.block_by_hash[previous_hash]
            reverse_chain.append(block)
        return reversed(reverse_chain)

    def public_key_balances_by_hash(self, head: Optional[bytes]) -> immutables.Map[PublicKey, PKBalance]:

        if head is None:
            return immutables.Map()

        public_key_balances: immutables.Map[PublicKey, PKBalance] = immutables.Map()
        unspent_transaction_outs: immutables.Map[OutputReference, Output] = immutables.Map()

        for block in self.chain_at_hash(head):

            public_key_balances = pkb_apply_block(unspent_transaction_outs,
                                                  public_key_balances,
                                                  block)

            unspent_transaction_outs = uto_apply_block(unspent_transaction_outs, block)

        return public_key_balances

    def __getitem__(self, key: bytes) -> immutables.Map[PublicKey, PKBalance]:
        if key not in self.cache:
            self.cache[key] = self.public_key_balances_by_hash(key)
        return self.cache[key]
