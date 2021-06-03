from io import BytesIO
import zipfile
import sys
import urllib.request
from pathlib import Path
from time import sleep, time
from typing import Any, Optional
import os
import tempfile
import logging
import argparse
import pickle

from skepticoin.datatypes import Block
from skepticoin.coinstate import CoinState
from skepticoin.networking.threading import NetworkingThread
from skepticoin.wallet import Wallet, save_wallet
from skepticoin.networking.peer import load_peers
from skepticoin.params import DESIRED_BLOCK_TIMESPAN


class DefaultArgumentParser(argparse.ArgumentParser):
    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.add_argument("--dont-listen", help="Don't listen for incoming connections", action="store_true")
        self.add_argument("--listening-port", help="Port to listen on", type=int, default=2412)
        self.add_argument("--log-to-file", help="Log to file", action="store_true")
        self.add_argument("--log-to-stdout", help="Log to stdout", action="store_true")


def initialize_peers_file() -> None:
    if not os.path.isfile("peers.json"):
        print("Creating new peers.json")
        with urllib.request.urlopen("https://pastebin.com/raw/CcfPX9mS") as response:
            with open("peers.json", "wb") as f:
                f.write(response.read())


def create_chain_dir() -> None:
    if not os.path.exists('chain'):
        print("Pre-download blockchain from trusted source to 'blockchain-master'")
        with urllib.request.urlopen("https://github.com/skepticoin/blockchain/archive/refs/heads/master.zip") as resp:
            with zipfile.ZipFile(BytesIO(resp.read())) as zip_ref:
                print("Extracting...")
                zip_ref.extractall()

        print("Created new directory for chain")
        os.rename('blockchain-master', 'chain')


def check_for_fresh_chain(thread: NetworkingThread) -> bool:
    # wait until your chain is no more than 20 typical block-sizes old before you start mining yourself
    waited = False
    try:
        while thread.local_peer.chain_manager.coinstate.head().timestamp + (20 * DESIRED_BLOCK_TIMESPAN) < time():
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


def read_chain_from_disk() -> CoinState:
    if os.path.isfile('chain.cache'):
        print("Reading cached chain")
        with open('chain.cache', 'rb') as file:
            coinstate = CoinState.load(lambda: pickle.load(file))
            height = len(coinstate.block_by_hash)
    else:
        coinstate = CoinState.zero()
        height = 0

    fresher_chain = sorted(os.listdir('chain'))[height:]
    print("Reading chain from disk, starting height=%d, fresher=%d" % (height, len(fresher_chain)))
    for filename in fresher_chain:
        height = int(filename.split("-")[0])
        if height % 1000 == 0:
            print(filename)

        try:
            with open(Path("chain") / filename, 'rb') as f:
                block = Block.stream_deserialize(f)
        except Exception as e:
            raise Exception("Corrupted block on disk: %s" % filename) from e

        coinstate = coinstate.add_block_no_validation(block)

    if fresher_chain:
        print("Caching chain for faster loading next time")
        # Currently this takes about 2 seconds.
        # It could be optimized further if we switch to an appendable file format for the cache.
        with open('chain.cache', 'wb') as file:
            coinstate.dump(lambda data: pickle.dump(data, file))

    return coinstate


def open_or_init_wallet() -> Wallet:
    if os.path.isfile("wallet.json"):
        wallet = Wallet.load(open("wallet.json", "r"))
    else:
        wallet = Wallet.empty()
        wallet.generate_keys(10_000)
        save_wallet(wallet)
        print("Created new wallet w/ 10.000 keys")

    return wallet


def start_networking_peer_in_background(
    args: Any, coinstate: CoinState
) -> NetworkingThread:
    print("Starting networking peer in background")
    port: Optional[int] = None if args.dont_listen else args.listening_port
    thread = NetworkingThread(coinstate, port)
    thread.local_peer.network_manager.disconnected_peers = load_peers()
    thread.start()
    return thread


def configure_logging_for_file() -> None:
    log_filename = Path(tempfile.gettempdir()) / ("skepticoin-networking-%s.log" % int(time()))
    FORMAT = '%(asctime)s %(message)s'
    logging.basicConfig(format=FORMAT, stream=open(log_filename, "w"), level=logging.INFO)


def configure_logging_for_stdout() -> None:
    FORMAT = "%(asctime)s %(message)s"
    logging.basicConfig(format=FORMAT, stream=sys.stdout, level=logging.INFO)


def configure_logging_from_args(args: Any) -> None:
    if args.log_to_file:
        configure_logging_for_file()

    if args.log_to_stdout:
        configure_logging_for_stdout()
