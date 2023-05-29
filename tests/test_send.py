
from skepticoin.balances import get_balance
from skepticoin.consensus import validate_non_coinbase_transaction_by_itself, validate_non_coinbase_transaction_in_coinstate  # noqa: E501
from skepticoin.humans import human
from skepticoin.scripts.utils import DefaultArgumentParser, configure_logging_from_args, open_or_init_wallet, read_chain_from_disk  # noqa: E501
from skepticoin.signing import SECP256k1PublicKey
from skepticoin.wallet import create_spend_transaction, parse_address


def test_prepare_to_send():
    "Exercise a lot of send-related code, but don't actually send anything."

    parser = DefaultArgumentParser()
    args = parser.parse_args(args=[])
    configure_logging_from_args(args)

    coinstate = read_chain_from_disk()
    wallet = open_or_init_wallet()
    balance = get_balance(wallet, coinstate)

    public_key = wallet.get_annotated_public_key('test')
    address = "SKE" + human(public_key) + "PTI"

    target_address = SECP256k1PublicKey(parse_address(address))
    change_address = SECP256k1PublicKey(wallet.get_annotated_public_key("change"))

    if balance == 0:
        print("Insufficient funds to finish this testcase")
        return

    value = 1

    transaction = create_spend_transaction(
        wallet,
        coinstate,
        value,
        0,  # we'll get to paying fees later
        target_address,
        change_address,
    )

    validate_non_coinbase_transaction_by_itself(transaction)
    assert coinstate.current_chain_hash
    validate_non_coinbase_transaction_in_coinstate(transaction, coinstate.current_chain_hash, coinstate)
