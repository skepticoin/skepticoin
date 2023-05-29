"""
The general theme of these tests is: let's do some end-to-end tests, so we at least hit a lot of code paths and expose
the most obvious of mistakes.
"""

from typing import Dict, Tuple
import pytest
from time import time
import logging
from time import sleep
import socket

from skepticoin.signing import SignableEquivalent, SECP256k1PublicKey
from skepticoin.datatypes import Transaction, Input, Output, OutputReference
from skepticoin.coinstate import CoinState
from skepticoin.networking.messages import InventoryMessage
from skepticoin.networking.threading import NetworkingThread
from skepticoin.networking.remote_peer import DisconnectedRemotePeer, RemotePeer, load_peers_from_list

from tests.test_db import read_test_chain_from_disk, setup_test_db


class FakeDiskInterface:
    def save_block(self, block):
        pass

    def write_peers(self, remote_peer: RemotePeer):
        pass

    def load_peers(self) -> Dict[Tuple[str, int, str], DisconnectedRemotePeer]:
        return {}

    def save_transaction_for_debugging(self, transaction):
        pass


def _try_to_connect(host, port):
    # just a blocking connect to check that a server is up and listening, then close the connection.
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect_ex((host, port))
    sock.close()


def test_ibd_integration(caplog):
    # just testing the basics: if we set up 2 threads, one with a coinstate, and one without, will the chain propagate?

    caplog.set_level(logging.INFO)

    coinstate1 = read_test_chain_from_disk(5, "ibd1")
    assert coinstate1.head().height == 5

    coinstate2 = CoinState(setup_test_db("ibd2"))

    thread_a = NetworkingThread(coinstate1, 12412, FakeDiskInterface())
    thread_a.start()

    _try_to_connect('127.0.0.1', 12412)

    thread_b = NetworkingThread(coinstate2, 12413, FakeDiskInterface())
    thread_b.local_peer.network_manager.disconnected_peers = load_peers_from_list([('127.0.0.1', 12412, "OUTGOING")])
    thread_b.start()

    try:
        start_time = time()
        while True:
            if thread_b.local_peer.chain_manager.coinstate.head().height >= 5:
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


def test_broadcast_transaction(caplog, mocker):
    # just testing the basics: is a broadcast transaction stored in the transaction pool on the other side?

    # By turning off transaction-validation, we can use an invalid transaction in this test.
    mocker.patch("skepticoin.networking.manager.validate_non_coinbase_transaction_by_itself")
    mocker.patch("skepticoin.networking.manager.validate_non_coinbase_transaction_in_coinstate")

    caplog.set_level(logging.INFO)

    coinstate1 = read_test_chain_from_disk(5, "int1")
    coinstate2 = read_test_chain_from_disk(5, "int2")

    thread_a = NetworkingThread(coinstate1, 12412, FakeDiskInterface())
    thread_a.start()

    _try_to_connect('127.0.0.1', 12412)

    thread_b = NetworkingThread(coinstate2, 12413, FakeDiskInterface())
    thread_b.local_peer.network_manager.disconnected_peers = load_peers_from_list([('127.0.0.1', 12412, "OUTGOING")])
    thread_b.start()

    previous_hash = coinstate1.block_by_height_at_head(0).transactions[0].hash()

    # Not actually a valid transaction (not signed)
    transaction = Transaction(
        inputs=[Input(OutputReference(previous_hash, 0), SignableEquivalent())],
        outputs=[Output(10, SECP256k1PublicKey(b'x' * 64))],
    )

    try:
        # give both peers some time to find each other
        start_time = time()
        while True:
            if (len(thread_a.local_peer.network_manager.get_active_peers()) > 0 and
                    len(thread_b.local_peer.network_manager.get_active_peers()) > 0):
                break

            if time() > start_time + 5:
                print("\n".join(str(r) for r in caplog.records))
                raise Exception("Peers can't connect")

            sleep(0.01)

        # broadcast_transaction... the part that we're testing
        thread_a.local_peer.network_manager.broadcast_transaction(transaction)

        # wait until it's picked up on the other side
        start_time = time()
        while True:
            if len(thread_b.local_peer.chain_manager.transaction_pool) > 0:
                break

            if time() > start_time + 5:
                print("\n".join(str(r) for r in caplog.records))
                raise Exception("Transaction broadcast failed")

            sleep(0.01)

    finally:
        thread_a.stop()
        thread_a.join()

        thread_b.stop()
        thread_b.join()


@pytest.mark.skip(reason="fickle test")
def test_broadcast_message_closed_connection_handling(caplog, mocker):
    caplog.set_level(logging.INFO)

    coinstate = read_test_chain_from_disk(5)

    thread_a = NetworkingThread(coinstate, 12412, FakeDiskInterface())
    thread_a.start()

    _try_to_connect('127.0.0.1', 12412)

    thread_b = NetworkingThread(coinstate, 12413, FakeDiskInterface())
    thread_b.local_peer.network_manager.disconnected_peers = load_peers_from_list([('127.0.0.1', 12412, "OUTGOING")])
    thread_b.start()

    try:
        # give both peers some time to find each other
        start_time = time()
        while True:
            if (len(thread_a.local_peer.network_manager.get_active_peers()) > 0 and
                    len(thread_b.local_peer.network_manager.get_active_peers()) > 0):
                break

            if time() > start_time + 5:
                print("\n".join(str(r) for r in caplog.records))
                raise Exception("Peers can't connect")

            sleep(0.01)

        # do a hard disconnect (without going through local_peer.disconnect)
        for remote_peer in thread_a.local_peer.network_manager.get_active_peers():
            remote_peer.sock.close()

        # broadcast a message
        thread_a.local_peer.network_manager.broadcast_message(InventoryMessage([]))

        # the error should have been logged
        assert len([r for r in caplog.records if 'ChainManager.broadcast_message' in str(r)]) > 0

    finally:
        thread_a.stop()
        thread_a.join()

        thread_b.stop()
        thread_b.join()
