
from skepticoin.balances import get_balance, get_output_if_not_consumed, get_public_key_balances
from skepticoin.scripts.utils import open_or_init_wallet, read_chain_from_disk


def test_balances():
    coinstate = read_chain_from_disk()
    wallet = open_or_init_wallet()
    balance = get_balance(wallet, coinstate)

    if balance == 0:
        print("Insufficient funds to finish this testcase")
        return

    pkb = get_public_key_balances(wallet, coinstate)

    for public_key, pk_balance in pkb.items():
        print(public_key, pk_balance.value, pk_balance.output_references, "\n")
        for output_reference in pk_balance.output_references:
            out = get_output_if_not_consumed(coinstate.blockstore,
                                             output_reference,
                                             coinstate.get_block_id_path(coinstate.current_chain_hash))
            print('output_reference = ', output_reference, out)
