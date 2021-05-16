# This quickly cobbled together script was used to create the Skepticoin Blockchain Explorer
# https://github.com/skepticoin/explorer/blob/master/README.md

from decimal import Decimal
from datetime import datetime, timezone
import os
import immutables
from collections import namedtuple
from pathlib import Path

from skepticoin.datatypes import OutputReference
from skepticoin.humans import human
from skepticoin.params import SASHIMI_PER_COIN


PKBalance2 = namedtuple('PKBalance2', [
    'value',
    'all_output_references',
    'unspent_output_references',
    'spent_in_transactions',
])


def show_coin(sashimi):
    return "%.08f SKEPTI" % (Decimal(sashimi) / SASHIMI_PER_COIN)


def pkb2_apply_transaction(unspent_transaction_outs, public_key_balances, transaction, is_coinbase):
    with public_key_balances.mutate() as mutable_public_key_balances:
        # for coinbase we must skip the input-removal because the input references "thin air" rather than an output.
        if not is_coinbase:
            for input in transaction.inputs:
                previously_unspent_output = unspent_transaction_outs[input.output_reference]

                public_key = previously_unspent_output.public_key
                mutable_public_key_balances[public_key] = PKBalance2(
                    value=mutable_public_key_balances[public_key].value - previously_unspent_output.value,
                    all_output_references=mutable_public_key_balances[public_key].all_output_references,
                    unspent_output_references=([to for to in
                                                mutable_public_key_balances[public_key].unspent_output_references
                                                if to != input.output_reference]),

                    # in principle a single public_key could be spent more than once in a single transaction, we
                    # could change the below into a set (or alternatively, note an input index)
                    spent_in_transactions=mutable_public_key_balances[public_key].spent_in_transactions + [transaction],
                )

        for i, output in enumerate(transaction.outputs):
            output_reference = OutputReference(transaction.hash(), i)

            if output.public_key not in mutable_public_key_balances:
                mutable_public_key_balances[output.public_key] = PKBalance2(0, [], [], [])

            mutable_public_key_balances[output.public_key] = PKBalance2(
                value=mutable_public_key_balances[output.public_key].value + output.value,

                all_output_references=(mutable_public_key_balances[output.public_key].all_output_references +
                                       [output_reference]),

                unspent_output_references=(mutable_public_key_balances[output.public_key].unspent_output_references +
                                           [output_reference]),

                spent_in_transactions=mutable_public_key_balances[output.public_key].spent_in_transactions,
            )

        return mutable_public_key_balances.finish()


def pkb2_apply_block(unspent_transaction_outs, public_key_balances, block):
    public_key_balances = pkb2_apply_transaction(
        unspent_transaction_outs, public_key_balances, block.transactions[0], is_coinbase=True)

    for transaction in block.transactions[1:]:
        public_key_balances = pkb2_apply_transaction(unspent_transaction_outs, public_key_balances, transaction, False)

    return public_key_balances


def get_unspent_transaction_outs_before_block(coinstate, block):
    if block.previous_block_hash == b'\00' * 32:
        return immutables.Map()
    return coinstate.unspent_transaction_outs_by_hash[block.previous_block_hash]


def build_pkb2_block(coinstate, block, public_key_balances_2):
    # TODO factor this away.
    unspent_transaction_outs = get_unspent_transaction_outs_before_block(coinstate, block)
    return pkb2_apply_block(unspent_transaction_outs, public_key_balances_2, block)


def build_pkb2(coinstate):
    public_key_balances_2 = immutables.Map()

    for height in range(coinstate.head().height + 1):
        block = coinstate.at_head.block_by_height[height]
        public_key_balances_2 = build_pkb2_block(coinstate, block, public_key_balances_2)

    return public_key_balances_2


def build_explorer(coinstate):
    assert os.getenv("EXPLORER_DIR")
    explorer_dir = Path(os.getenv("EXPLORER_DIR"))

    public_key_balances_2 = immutables.Map()

    for height in range(coinstate.head().height + 1):
        print("Block", height)
        block = coinstate.at_head.block_by_height[height]
        potential_message = block.transactions[0].inputs[0].signature.signature

        if all([(32 <= b < 127) or (b == 10) for b in potential_message]):
            msg = "```\n" + str(potential_message, encoding="ascii") + "\n```"
        else:
            msg = ""

        unspent_transaction_outs = get_unspent_transaction_outs_before_block(coinstate, block)
        public_key_balances_2 = build_pkb2_block(coinstate, block, public_key_balances_2)

        with open(explorer_dir / (human(block.hash()) + '.md'), 'w') as block_f:

            block_f.write(f"""## Block {human(block.hash())}

Attribute | Value
--- | ---
Height | {block.height}
Hash | {human(block.hash())}
Timestamp | {datetime.fromtimestamp(block.timestamp, tz=timezone.utc).isoformat()}
Target | {human(block.target)}
Merke root | {human(block.merkle_root_hash)}
Nonce | {block.nonce}

{msg}

### Transactions

Hash | Amount
--- | ---
""")

            for transaction in block.transactions:
                h = human(transaction.hash())
                v = show_coin(sum(o.value for o in transaction.outputs))
                block_f.write(f"""[{h}]({h}.md) | {v} \n""")

                with open(explorer_dir / (human(transaction.hash()) + ".md"), 'w') as transaction_f:
                    transaction_f.write(f"""## Transaction {human(transaction.hash())}

In block [{human(block.hash())}]({human(block.hash())}.md)

### Inputs

Transaction | Output Index | Value | Address
--- | --- | --- | ---
""")
                    for input in transaction.inputs:
                        output_reference = input.output_reference
                        if output_reference.hash != 32 * b'\x00':
                            output = unspent_transaction_outs[output_reference]
                            h = human(output_reference.hash)
                            v = show_coin(output.value)
                            a = "SKE" + human(output.public_key.public_key) + "PTI"

                            transaction_f.write(f"""[{h}]({h}.md) | {output_reference.index} | """
                                                f"""{v} | [{a}]({a}.md)\n""")
                        else:
                            h = human(output_reference.hash)
                            v = ""
                            a = "Thin Air"

                            transaction_f.write(f"""{h} | {output_reference.index} | """
                                                f"""{v} | {a}\n""")

                    transaction_f.write("""### Outputs

Value | Address
--- | ---
""")
                    for output in transaction.outputs:
                        v = show_coin(output.value)
                        a = "SKE" + human(output.public_key.public_key) + "PTI"

                        transaction_f.write(f"""{v} | [{a}]({a}.md)\n""")

    for pk, pkb2 in public_key_balances_2.items():
        v = show_coin(pkb2.value)
        address = "SKE" + human(pk.public_key) + "PTI"
        with open(explorer_dir / (address + ".md"), 'w') as address_f:
            address_f.write(f"""## {address}

Current balance: {v}
(as of block {coinstate.head().height})

## Received in

Transaction | Output Index
--- | ---
""")
            for output_reference in pkb2.all_output_references:
                h = human(output_reference.hash)
                address_f.write(f"""[{h}]({h}.md) | {output_reference.index}\n""")

            if len(pkb2.spent_in_transactions) > 0:
                address_f.write("""
## Spent in

Transaction | ...
--- | ---
""")

                for transaction in pkb2.spent_in_transactions:
                    address_f.write(f"""{human(transaction.hash())} | ...\n""")

            else:
                address_f.write("""
## Spent in

-- not spent --
""")


build_explorer(get_coinstate())  # noqa F821  (get_coinstate is a globally available variable in skepticoin-run)
