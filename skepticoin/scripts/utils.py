from skepticoin.blockstore import BlockStore
import sys
from pathlib import Path
from time import sleep, time
from typing import Any, Optional
import os
import tempfile
import logging
import argparse

from skepticoin.coinstate import CoinState
from skepticoin.networking.threading import NetworkingThread
from skepticoin.wallet import Wallet, save_wallet

DEFAULT_BLOCKSTORE_FILE_PATH = "blocks.db"


class DefaultArgumentParser(argparse.ArgumentParser):
    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.add_argument("--dont-listen", help="Don't listen for incoming connections", action="store_true")
        self.add_argument("--listening-port", help="Port to listen on", type=int, default=2412)
        self.add_argument("--log-to-file", help="Log to file", action="store_true")
        self.add_argument("--log-to-stdout", help="Log to stdout", action="store_true")


def check_chain_dir() -> None:
    if os.path.exists('chain'):
        print('Your ./chain/ directory is no longer needed: please delete it to stop this reminder.')


def wait_for_fresh_chain(thread: NetworkingThread, freshness: int) -> None:
    """
    Wait until your chain is no more than specified seconds old before you start mining yourself
    """
    while thread.local_peer.chain_manager.coinstate.head().timestamp + freshness < time():
        thread.local_peer.show_stats()
        diff = int(time() - thread.local_peer.chain_manager.coinstate.head().timestamp)
        print(f"Waiting for fresh chain (your chain is {diff:,} seconds, too old for my tastes)")
        sleep(10)


def read_chain_from_disk() -> CoinState:

    coinstate = CoinState(BlockStore(DEFAULT_BLOCKSTORE_FILE_PATH))

    # It is no longer possible to load old files, due to pickle issues not worth solving.

    if os.path.isfile('chain.cache'):
        print("Old chain.cache file found (ignored)")

    if os.path.isdir('chain'):
        print("Old chain folder found (ignored)")

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
    thread.start()
    return thread


def configure_logging_for_file() -> None:
    log_filename = Path(tempfile.gettempdir()) / ("skepticoin-networking-%s.log" % int(time()))
    print('Logging to file: %s' % log_filename)
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
