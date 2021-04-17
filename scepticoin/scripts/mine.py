from pathlib import Path
import logging
import sys
from decimal import Decimal
import random

from scepticoin.params import SASHIMI_PER_COIN
from scepticoin.consensus import construct_block_for_mining
from scepticoin.signing import SECP256k1PublicKey
from scepticoin.wallet import save_wallet
from scepticoin.utils import block_filename
from time import time

from .utils import (
    initialize_peers_file,
    create_chain_dir,
    read_chain_from_disk,
    open_or_init_wallet,
    start_networking_peer_in_background,
    check_for_fresh_chain,
)


def main():
    if "--log-networking" in sys.argv:
        log_filename = "/tmp/scepticoin-networking.log"
        FORMAT = '%(asctime)s %(message)s'
        logging.basicConfig(format=FORMAT, stream=open(log_filename, "w"), level=logging.INFO)
        print("Logging on", log_filename)

    create_chain_dir()
    coinstate = read_chain_from_disk()
    wallet = open_or_init_wallet()
    initialize_peers_file()
    thread = start_networking_peer_in_background(coinstate)

    while True:
        if check_for_fresh_chain(thread):
            print("Starting mining")

        public_key = wallet.get_annotated_public_key("reserved for potentially mined block")
        save_wallet(wallet)

        nonce = random.randrange(1 << 32)
        while True:
            coinstate, transactions = thread.local_peer.chain_manager.get_state()
            increasing_time = max(int(time()), coinstate.head().timestamp + 1)
            block = construct_block_for_mining(
                coinstate, transactions, SECP256k1PublicKey(public_key), increasing_time, b'', nonce)
            nonce = (nonce + 1) % (1 << 32)
            if block.hash() < block.target:
                break

        coinstate = coinstate.add_block(block, int(time()))
        with open(Path('chain') / block_filename(block), 'wb') as f:
            f.write(block.serialize())
        print("FOUND", block_filename(block))
        print("Your wallet now contains %s scepticoin" % (wallet.get_balance(coinstate) / Decimal(SASHIMI_PER_COIN)))

        thread.local_peer.chain_manager.set_coinstate(coinstate)
        thread.local_peer.network_manager.broadcast_block(block)

    thread.stop()
