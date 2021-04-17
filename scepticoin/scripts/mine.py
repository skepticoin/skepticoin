import urllib.request
import logging
import sys
from decimal import Decimal
import shutil
import os
import random

from scepticoin.params import SASHIMI_PER_COIN
from scepticoin.consensus import construct_block_for_mining
from scepticoin.signing import SECP256k1PublicKey
from scepticoin.datatypes import Block
from scepticoin.coinstate import CoinState
from scepticoin.networking.threading import NetworkingThread
from scepticoin.wallet import Wallet
from scepticoin.utils import block_filename
from scepticoin.networking.utils import load_peers
from time import time, sleep


def initialize_peers_file():
    if not os.path.isfile("peers.json"):
        print("Creating new peers.json")
        with urllib.request.urlopen("https://pastebin.com/raw/CcfPX9mS") as response:
            with open("peers.json", "wb") as f:
                f.write(response.read())


def save_wallet(wallet):
    with open("wallet.json.new", 'w') as f:
        wallet.dump(f)
        # TODO To provide a more "living on the edge" experience we should get rid of this atomic operation to increase
        # the number of ways wallets can get corrupted
        shutil.move("wallet.json.new", "wallet.json")


def check_for_fresh_chain(thread):
    # wait until your chain is no more than 5 minutes old before you start mining yourself
    waited = False
    while thread.local_peer.chain_manager.coinstate.head().timestamp + (5 * 60) < time():
        waited = True
        try:
            thread.local_peer.show_stats()
            print("Waiting for fresh chain; press ^C to stop waiting and just mine")
            sleep(10)
        except KeyboardInterrupt:
            break
    return waited


def main():
    if "--log-networking" in sys.argv:
        log_filename = "/tmp/scepticoin-networking.log"
        FORMAT = '%(asctime)s %(message)s'
        logging.basicConfig(format=FORMAT, stream=open(log_filename, "w"), level=logging.INFO)
        print("Logging on", log_filename)

    if not os.path.exists('chain'):
        print("Created new directory for chain")
        os.makedirs('chain')

    initialize_peers_file()

    print("Reading chain from disk")
    coinstate = CoinState.zero()
    for filename in sorted(os.listdir('chain')):
        height = int(filename.split("-")[0])
        if height % 1000 == 0:
            print(filename)

        block = Block.stream_deserialize(open('chain/%s' % filename, 'rb'))
        coinstate = coinstate.add_block_no_validation(block)

    try:
        wallet = Wallet.load(open("wallet.json", "r"))
    except Exception:  # bwegh
        wallet = Wallet.empty()
        wallet.generate_keys(10_000)
        save_wallet(wallet)
        print("Created new wallet w/ 10.000 keys")

    print("Starting networking peer in background")
    thread = NetworkingThread(coinstate, 2412)
    thread.local_peer.network_manager.disconnected_peers = load_peers()
    thread.start()

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
        with open('chain/%s' % block_filename(block), 'wb') as f:
            f.write(block.serialize())
        print("FOUND", block_filename(block))
        print("Your wallet now contains %s scepticoin" % (wallet.get_balance(coinstate) / Decimal(SASHIMI_PER_COIN)))

        thread.local_peer.chain_manager.set_coinstate(coinstate)
        thread.local_peer.network_manager.broadcast_block(block)

    thread.stop()
