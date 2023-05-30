
from typing import List, Optional

import immutables
from skepticoin.blockstore import BlockStore
from skepticoin.coinstate import CoinState

from skepticoin.datatypes import Output, OutputReference, Transaction
from skepticoin.signing import PublicKey, SECP256k1PublicKey
from skepticoin.wallet import Wallet
import itertools


class PKBalance:

    def __init__(self, value: int, output_references: List[OutputReference]):
        self.value = value
        self.output_references = output_references

    def __repr__(self) -> str:
        return "PKBalance(value=%s, output_references=%s)" % (self.value, self.output_references)


def get_public_key_balances(wallet: Wallet, coinstate: CoinState) -> immutables.Map[PublicKey, PKBalance]:

    public_keys = [SECP256k1PublicKey(pk).serialize() for pk in wallet.keypairs.keys()]
    chain_index = set(coinstate.get_block_id_path(coinstate.current_chain_hash))

    candidate_transaction_pairs = coinstate.blockstore.sql(f"""
            SELECT txo.transaction_hash, txo.seq, txo.value, txo.public_key,
                   output_block.block_id, input_block.block_id
                FROM transaction_outputs txo
                JOIN transaction_locator tlo ON(tlo.transaction_hash = txo.transaction_hash)
                JOIN chain output_block ON(tlo.block_hash = output_block.block_hash)
                LEFT OUTER JOIN transaction_inputs txi ON (
                    txo.transaction_hash = txi.output_reference_hash AND
                    txo.seq = txi.output_reference_index
                )
                LEFT OUTER JOIN transaction_locator tli ON(
                    tli.transaction_hash = txi.transaction_hash)
                LEFT OUTER JOIN chain input_block ON(
                    tli.block_hash = input_block.block_hash)
                WHERE txo.public_key IN ({", ".join(["?"] * len(public_keys))})
        """, public_keys)  # type: ignore

    utxo = [row for row in candidate_transaction_pairs
            if row[4] in chain_index and row[5] not in chain_index]

    group_by_public_key = {
        k: list(v) for k, v in itertools.groupby(utxo, lambda row: row[3])  # type: ignore
    }

    return immutables.Map({
        PublicKey.deserialize(public_key): PKBalance(
            sum(row[2] for row in grouped_rows),
            [OutputReference(row[0], row[1]) for row in grouped_rows]
        ) for (public_key, grouped_rows) in group_by_public_key.items()
    })


def get_balance(wallet: Wallet, coinstate: CoinState) -> int:
    return sum(balance.value for balance in get_public_key_balances(wallet, coinstate).values())


def get_output_if_not_consumed(
        blockstore: BlockStore, ref: OutputReference, chain_index: List[int]
) -> Optional[Output]:

    cross_chain_outs = blockstore.sql("""
            SELECT value, public_key, chain.block_id
            FROM transaction_outputs txo
            JOIN transaction_locator USING (transaction_hash)
            JOIN chain USING(block_hash)
            WHERE transaction_hash = ? AND seq = ?
    """, (ref.hash, ref.index))  # type: ignore

    outs = [out for out in cross_chain_outs if out[2] in chain_index]

    assert len(outs) == 1

    (value, public_key) = outs[0][:2]

    ins = blockstore.sql("""
            SELECT chain.block_id
            FROM transaction_inputs txi
            JOIN transaction_locator USING(transaction_hash)
            JOIN chain USING(block_hash)
            WHERE output_reference_hash = ? AND output_reference_index = ?
    """, (ref.hash, ref.index))  # type: ignore

    ins = [i for i in ins if i[0] in chain_index]

    if len(ins) > 0:
        # normal: the output has been consumed
        assert len(ins) == 1
        return None

    return Output(value, PublicKey.deserialize(public_key))


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
