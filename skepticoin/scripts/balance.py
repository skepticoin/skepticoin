from datetime import datetime
from time import sleep

from skepticoin.validator import Validator
from skepticoin.balances import get_balance

from .utils import (
    open_or_init_wallet,
    read_chain_from_disk,
    configure_logging_from_args,
    start_networking_peer_in_background,
    wait_for_fresh_chain,
    DefaultArgumentParser,
)

from ..params import SASHIMI_PER_COIN


def main() -> None:
    parser = DefaultArgumentParser()
    args = parser.parse_args()
    configure_logging_from_args(args)

    coinstate = read_chain_from_disk()
    wallet = open_or_init_wallet()

    # we need a fresh chain because our wallet doesn't track spending/receiving, so we need to look at the real
    # blockchain to know the most current balance.
    thread = start_networking_peer_in_background(args, coinstate)

    wait_for_fresh_chain(thread, freshness=300)
    coinstate = thread.local_peer.chain_manager.coinstate

    print("Chain up to date")

    print(
        get_balance(wallet, coinstate) / SASHIMI_PER_COIN, "SKEPTI at h. %s," % coinstate.head().height,
        datetime.fromtimestamp(coinstate.head().timestamp).isoformat())

    validator = Validator()
    while coinstate.blockstore.validation_queue_size() > 0:
        print(
            "Chain validation is %s blocks behind. Balance could change if validation fails." %
            coinstate.blockstore.validation_queue_size())

        validator.step(thread.local_peer.chain_manager)
        sleep(1)

    print("Waiting for networking thread to exit.")
    thread.stop()
    thread.join()
