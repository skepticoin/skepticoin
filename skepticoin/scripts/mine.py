from pathlib import Path
from decimal import Decimal
import random

from skepticoin.params import SASHIMI_PER_COIN
from skepticoin.consensus import construct_block_for_mining
from skepticoin.signing import SECP256k1PublicKey
from skepticoin.wallet import save_wallet
from skepticoin.utils import block_filename
from skepticoin.cheating import MAX_KNOWN_HASH_HEIGHT
from time import time

from .utils import (
    initialize_peers_file,
    create_chain_dir,
    read_chain_from_disk,
    open_or_init_wallet,
    start_networking_peer_in_background,
    check_for_fresh_chain,
    configure_logging_from_args,
    DefaultArgumentParser,
)


def main():
    parser = DefaultArgumentParser()
    args = parser.parse_args()
    configure_logging_from_args(args)

    create_chain_dir()
    coinstate = read_chain_from_disk()
    wallet = open_or_init_wallet()
    initialize_peers_file()
    thread = start_networking_peer_in_background(args, coinstate)
    thread.local_peer.show_stats()

    if check_for_fresh_chain(thread):
        thread.local_peer.show_stats()

    if thread.local_peer.chain_manager.coinstate.head().height <= MAX_KNOWN_HASH_HEIGHT:
        print("Your blockchain is not just old, it is ancient; ABORTING")
        return

    print("Starting mining: A repeat minter")

    try:
        print("Starting main loop")

        while True:
            public_key = wallet.get_annotated_public_key("reserved for potentially mined block")
            save_wallet(wallet)

            nonce = random.randrange(1 << 32)
            last_round_second = int(time())
            i = 0

            while True:
                if int(time()) > last_round_second:
                    print("Hashrate:", i)
                    last_round_second = int(time())
                    i = 0

                coinstate, transactions = thread.local_peer.chain_manager.get_state()
                increasing_time = max(int(time()), coinstate.head().timestamp + 1)
                block = construct_block_for_mining(
                    coinstate, transactions, SECP256k1PublicKey(public_key), increasing_time, b'', nonce)

                i += 1
                nonce = (nonce + 1) % (1 << 32)
                if block.hash() < block.target:
                    break

            coinstate = coinstate.add_block(block, int(time()))
            with open(Path('chain') / block_filename(block), 'wb') as f:
                f.write(block.serialize())
            print("FOUND", block_filename(block))
            print("Wallet balance: %s skepticoin" % (wallet.get_balance(coinstate) / Decimal(SASHIMI_PER_COIN)))

            thread.local_peer.chain_manager.set_coinstate(coinstate)
            thread.local_peer.network_manager.broadcast_block(block)

    except KeyboardInterrupt:
        print("KeyboardInterrupt")
    finally:
        print("Stopping networking thread")
        thread.stop()
        print("Waiting for networking thread to stop")
        thread.join()
        print("Done; waiting for Python-exit")
