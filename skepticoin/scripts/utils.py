from skepticoin.networking.disk_interface import DiskInterface
import sys
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
from skepticoin.humans import computer, human


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


def wait_for_fresh_chain(thread: NetworkingThread) -> None:
    """
    Wait until your chain is no more than 10 days old before you start mining yourself
    """
    while thread.local_peer.chain_manager.coinstate.head().timestamp + (10 * 24 * 60 * 60) < time():
        thread.local_peer.show_stats()
        diff = int(time() - thread.local_peer.chain_manager.coinstate.head().timestamp + (10 * 24 * 60 * 60))
        print(f"Waiting for fresh chain (your chain is {diff:,} seconds too old for my tastes)")
        sleep(10)


def read_chain_from_disk() -> CoinState:
    if os.path.isfile('chain.cache'):
        print("Reading cached chain")
        with open('chain.cache', 'rb') as file:
            coinstate = CoinState.load(lambda: pickle.load(file))
    else:
        coinstate = CoinState.zero()

    rewrite = False

    if os.path.isdir('chain'):
        # the code below is no longer needed by normal users, but some old testcases still rely on it:
        for filename in sorted(os.listdir('chain')):
            (height_str, hash_str) = filename.split("-")
            (height, hash) = (int(height_str), computer(hash_str))

            if hash not in coinstate.block_by_hash:

                if height % 1000 == 0:
                    print(filename)

                if os.path.getsize(f"chain/{filename}") == 0:
                    print("Stopping at empty block file: %s" % filename)
                    break

                with open(Path("chain") / filename, 'rb') as f:
                    try:
                        block = Block.stream_deserialize(f)
                    except Exception as e:
                        raise Exception("Corrupted block on disk: %s" % filename) from e
                    try:
                        coinstate = coinstate.add_block_no_validation(block)
                    except Exception:
                        print("Failed to add block at height=%d, previous_hash=%s"
                              % (block.height, human(block.header.summary.previous_block_hash)))
                        break

                rewrite = True

    if rewrite:
        DiskInterface().write_chain_cache_to_disk(coinstate)

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
