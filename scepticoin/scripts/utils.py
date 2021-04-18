import urllib.request
from pathlib import Path
import os

from scepticoin.datatypes import Block
from scepticoin.coinstate import CoinState
from scepticoin.networking.threading import NetworkingThread
from scepticoin.wallet import Wallet, save_wallet
from scepticoin.networking.utils import load_peers
from time import time, sleep


def initialize_peers_file():
    if not os.path.isfile("peers.json"):
        print("Creating new peers.json")
        with urllib.request.urlopen("https://pastebin.com/raw/CcfPX9mS") as response:
            with open("peers.json", "wb") as f:
                f.write(response.read())


def create_chain_dir():
    if not os.path.exists('chain'):
        print("Created new directory for chain")
        os.makedirs('chain')


def check_for_fresh_chain(thread):
    # wait until your chain is no more than 5 minutes old before you start mining yourself
    waited = False
    try:
        while thread.local_peer.chain_manager.coinstate.head().timestamp + (5 * 60) < time():
            waited = True
            thread.local_peer.show_stats()
            print("Waiting for fresh chain")
            sleep(10)

        while len(thread.local_peer.network_manager.get_active_peers()) == 0:
            waited = True
            thread.local_peer.show_stats()
            print("Waiting for peers")
            sleep(3)
    except KeyboardInterrupt:
        print("WAITING ABORTED... CONTINUING DESPITE FRESHNESS/CONNECTEDNESS!")

    return waited


def read_chain_from_disk():
    print("Reading chain from disk")
    coinstate = CoinState.zero()
    for filename in sorted(os.listdir('chain')):
        height = int(filename.split("-")[0])
        if height % 1000 == 0:
            print(filename)

        block = Block.stream_deserialize(open(Path('chain') / filename, 'rb'))
        coinstate = coinstate.add_block_no_validation(block)

    return coinstate


def open_or_init_wallet():
    try:
        wallet = Wallet.load(open("wallet.json", "r"))
    except Exception:  # bwegh
        wallet = Wallet.empty()
        wallet.generate_keys(10_000)
        save_wallet(wallet)
        print("Created new wallet w/ 10.000 keys")
    return wallet


def start_networking_peer_in_background(coinstate):
    print("Starting networking peer in background")
    thread = NetworkingThread(coinstate, 2412)
    thread.local_peer.network_manager.disconnected_peers = load_peers()
    thread.start()
    return thread
