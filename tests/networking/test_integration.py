"""
The general theme of these tests is: let's do some end-to-end tests, so we at least hit a lot of code paths and expose
the most obvious of mistakes.
"""

from time import time
import logging
from pathlib import Path
from time import sleep
import socket

from skepticoin.datatypes import Block
from skepticoin.coinstate import CoinState
from skepticoin.networking.threading import NetworkingThread
from skepticoin.networking.utils import load_peers_from_list

CHAIN_TESTDATA_PATH = Path(__file__).parent.joinpath("../testdata/chain")


class FakeDiskInterface:
    def save_block(self, block):
        pass

    def update_peer_db(self, remote_peer):
        pass

    def save_transaction_for_debugging(self, transaction):
        pass


def _read_chain_from_disk(max_height):
    coinstate = CoinState.zero()

    for file_path in sorted(CHAIN_TESTDATA_PATH.iterdir()):
        height = int(file_path.name.split("-")[0])
        if height > max_height:
            return coinstate

        block = Block.stream_deserialize(open(file_path, 'rb'))
        coinstate = coinstate.add_block_no_validation(block)

    return coinstate


def _try_to_connect(host, port):
    # just a blocking connect to check that a server is up and listening, then close the connection.
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect_ex((host, port))
    sock.close()


def test_ibd_integration(caplog):
    # just testing the basics: if we set up 2 threads, one with a coinstate, and one without, will the chain propagate?

    caplog.set_level(logging.INFO)

    coinstate = _read_chain_from_disk(5)

    thread_a = NetworkingThread(coinstate, 12412, FakeDiskInterface())
    thread_a.start()

    _try_to_connect('127.0.0.1', 12412)

    thread_b = NetworkingThread(CoinState.zero(), 12413, FakeDiskInterface())
    thread_b.local_peer.network_manager.disconnected_peers = load_peers_from_list([('127.0.0.1', 12412, "OUTGOING")])
    thread_b.start()

    try:
        start_time = time()
        while True:
            if thread_b.local_peer.chain_manager.coinstate.head().height == 5:
                break

            if time() > start_time + 5:
                print("\n".join(str(r) for r in caplog.records))
                raise Exception("IBD failed")

            sleep(0.01)

    finally:
        thread_a.stop()
        thread_a.join()

        thread_b.stop()
        thread_b.join()
