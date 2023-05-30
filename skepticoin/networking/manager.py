from __future__ import annotations
from datetime import datetime
import traceback
from threading import Lock
from typing import Dict, List, Set, Tuple

from skepticoin.coinstate import CoinState

from skepticoin.humans import human
from skepticoin.consensus import (
    validate_no_duplicate_output_references_in_transactions,
    validate_non_coinbase_transaction_by_itself,
    validate_non_coinbase_transaction_in_coinstate,
    ValidateTransactionError,
)
from skepticoin.networking.disk_interface import DiskInterface

from .params import (
    IBD_REQUEST_LIFETIME,
    IBD_PEER_ACTIVITY_TIMEOUT,
    SWITCH_TO_ACTIVE_MODE_TIMEOUT,
)
from skepticoin.datatypes import Block, Transaction
from skepticoin.networking.remote_peer import ConnectedRemotePeer, DisconnectedRemotePeer, OUTGOING

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from skepticoin.networking.local_peer import LocalPeer

from .messages import (
    GetBlocksMessage,
    DataMessage,
    DATA_BLOCK,
    DATA_TRANSACTION,
)


class Manager:
    def step(self, current_time: int) -> None:
        raise NotImplementedError


class NetworkManager(Manager):

    def __init__(self, local_peer: LocalPeer, disk_interface: DiskInterface = DiskInterface()) -> None:
        self.local_peer = local_peer
        self.my_addresses: Set[Tuple[str, int]] = set()
        self.connected_peers: Dict[Tuple[str, int, str], ConnectedRemotePeer] = {}
        self.disconnected_peers: Dict[Tuple[str, int, str], DisconnectedRemotePeer] = {}
        self.disk_interface = disk_interface

    def _sanity_check(self) -> None:
        for key in self.connected_peers:
            if key in self.disconnected_peers:
                raise Exception("this shouldn't happen %s" % (key,))

    def step(self, current_time: int) -> None:
        # self.local_peer.logger.info("NetworkManager.step()")

        self._sanity_check()

        for disconnected_peer in list(self.disconnected_peers.values()):

            if (disconnected_peer.direction == OUTGOING and
                (disconnected_peer.host, disconnected_peer.port) not in self.my_addresses and
                    disconnected_peer.is_time_to_connect(current_time)):

                disconnected_peer.last_connection_attempt = current_time
                self.local_peer.start_outgoing_connection(disconnected_peer)

        for peer in list(self.connected_peers.values()):
            peer.step(current_time)

    def handle_peer_connected(self, remote_peer: ConnectedRemotePeer) -> None:
        self.local_peer.logger.info("%15s NetworkManager.handle_peer_connected()" % remote_peer.host)

        key = (remote_peer.host, remote_peer.port, remote_peer.direction)
        if key in self.connected_peers:
            self.local_peer.logger.warning("%15s duplicate peer %s" % (remote_peer.host, key))
            self.local_peer.disconnect(self.connected_peers[key], ValueError("duplicate"))  # just drop the existing one

        self._sanity_check()
        self.connected_peers[key] = remote_peer
        if key in self.disconnected_peers:
            del self.disconnected_peers[key]
        self._sanity_check()

    def handle_peer_disconnected(self, remote_peer: ConnectedRemotePeer) -> None:
        self.local_peer.logger.debug("%15s NetworkManager.handle_peer_disconnected()" % remote_peer.host)

        key = (remote_peer.host, remote_peer.port, remote_peer.direction)

        self._sanity_check()

        del self.connected_peers[key]

        if remote_peer.direction == OUTGOING:
            if not remote_peer.hello_received:
                remote_peer.ban_score += 1
                self.local_peer.logger.info('%15s Disconnected without hello, ban_score=%d'
                                            % (remote_peer.host, remote_peer.ban_score))

            self.disconnected_peers[key] = remote_peer.as_disconnected()

        self._sanity_check()

    def get_active_peers(self) -> List[ConnectedRemotePeer]:
        return [p for p in self.connected_peers.values()
                if p.hello_sent and p.hello_received and not p.connection_to_self]

    def broadcast_block(self, block: Block) -> None:
        self.local_peer.logger.info("%15s ChainManager.broadcast_block(%s)" % ("", human(block.hash())))
        self.broadcast_message(DataMessage(DATA_BLOCK, block))

    def broadcast_transaction(self, transaction: Transaction) -> None:
        self.broadcast_message(DataMessage(DATA_TRANSACTION, transaction))

    def broadcast_message(self, message: DataMessage) -> None:
        for peer in self.get_active_peers():
            try:
                # try/except b/c .send_message might try to set the selector for a just-closed sock to writing
                peer.send_message(message)
            except (ValueError, KeyError) as e:
                # ValueError, KeyError seen in the wild for selector problems; should be more exactly matched though.
                # The traceback that's printed below will help in this matching effort.

                self.local_peer.logger.info("%15s ChainManager.broadcast_message error %s" % (peer.host, e))
                if "ValueError: Invalid file descriptor: " not in str(e):
                    # be loud... this is likely a programming error.
                    self.local_peer.logger.warning(traceback.format_exc())

            except (OSError) as e:
                # OSError: e.g. ConnectionRefusedError, "Bad file descriptor"
                self.local_peer.logger.info("%15s ChainManager.broadcast_message error %s" % (peer.host, e))


def inventory_batch_handled(peer: ConnectedRemotePeer) -> bool:
    """Has the full loop GetBlocks -> Inventory -> GetData (n times) -> Data (n times) been completed?"""
    return not peer.waiting_for_inventory and peer.inventory_messages == []


class ChainManager(Manager):

    def __init__(self, local_peer: LocalPeer, current_time: int):
        self.local_peer = local_peer
        self.lock = Lock()
        self.coinstate: CoinState
        self.started_at = current_time
        self.transaction_pool: List[Transaction] = []

    def step(self, current_time: int) -> None:

        if not self.should_actively_fetch_blocks(current_time):
            return  # no manual action required, blocks expected to be sent to us instead.

        for peer in self.local_peer.network_manager.get_active_peers():
            if peer.waiting_for_inventory:
                assert peer.last_inventory_request_at != 0
                if current_time > peer.last_inventory_request_at + IBD_REQUEST_LIFETIME:
                    self.local_peer.disconnect(peer, ValueError(
                        "too long since IBD request sent @ %s" %
                        str(datetime.fromtimestamp(peer.last_inventory_request_at))))
                elif (peer.last_inventory_response_at != 0
                        and current_time >
                        peer.last_inventory_response_at + IBD_PEER_ACTIVITY_TIMEOUT):
                    self.local_peer.disconnect(peer, ValueError(
                        "too long since last IBD response received @ %s" %
                        str(datetime.fromtimestamp(peer.last_inventory_response_at))))

        # sort by last request time so we eventually loop over all peers
        peer_rotation_schedule = sorted(self.local_peer.network_manager.get_active_peers(),
                                        key=lambda p: p.last_inventory_request_at)

        if len(peer_rotation_schedule) == 0:
            return

        for peer in peer_rotation_schedule:
            if (current_time <
                    IBD_PEER_ACTIVITY_TIMEOUT +
                    max(peer.last_inventory_request_at,
                        peer.last_inventory_response_at)):
                return

        # pick the peer we haven't sent requests to in the longest time, and ask for blocks
        remote_peer = peer_rotation_schedule[0]

        get_blocks_message, height = self.get_get_blocks_message()

        remote_peer.waiting_for_inventory = True
        remote_peer.last_inventory_request_at = current_time
        remote_peer.last_inventory_response_at = 0

        self.local_peer.logger.info("%15s Requesting blocks at h. > %d" % (
            remote_peer.host, height))

        remote_peer.send_message(get_blocks_message)

    def should_actively_fetch_blocks(self, current_time: int) -> bool:

        return (
            (current_time > self.coinstate.head().timestamp + SWITCH_TO_ACTIVE_MODE_TIMEOUT)
            or (current_time <= self.started_at + 60)  # always sync w/ network right after restart
            or (current_time % 60 == 0)  # on average, every 1 minutes, do a network resync explicitly
        )

    def set_coinstate(self, coinstate: CoinState) -> None:
        with self.lock:
            self.local_peer.logger.info("%15s ChainManager.set_coinstate(%s)" % ("", coinstate))
            self.coinstate = coinstate
            self._cleanup_transaction_pool_for_coinstate(coinstate)

    def add_transaction_to_pool(self, transaction: Transaction) -> bool:
        with self.lock:
            self.local_peer.logger.info(
                "%15s ChainManager.add_transaction_to_pool(%s)" % ("", human(transaction.hash())))

            try:
                validate_non_coinbase_transaction_by_itself(transaction)

                assert self.coinstate.current_chain_hash

                validate_non_coinbase_transaction_in_coinstate(
                    transaction, self.coinstate.current_chain_hash, self.coinstate)

                # Horribly inefficiently implemented (AKA 'room for improvement)
                validate_no_duplicate_output_references_in_transactions(self.transaction_pool + [transaction])

                #  we don't do validate_no_duplicate_transactions here (assuming it's just been done before
                #  add_transaction_to_pool).

            except ValidateTransactionError as e:
                # TODO: dirty hack at this particular point... to allow for e.g. out-of-order transactions to not take
                # down the whole peer, but this should more specifically match for a short list of OK problems.
                self.local_peer.logger.warning("%15s INVALID transaction %s" % ("", str(e)))
                self.local_peer.disk_interface.save_transaction_for_debugging(transaction)

                return False  # not successful

            self.transaction_pool.append(transaction)

        return True  # successfully added

    def get_state(self) -> Tuple[CoinState, List[Transaction]]:
        with self.lock:
            return self.coinstate, self.transaction_pool

    def _cleanup_transaction_pool_for_coinstate(self, coinstate: CoinState) -> None:
        # This is really the simplest (though not most efficient mechanism): simply remove now-invalid transactions from
        # the pool
        def is_valid(transaction: Transaction) -> bool:
            try:
                assert self.coinstate.current_chain_hash

                # validate_non_coinbase_transaction_by_itself(transaction) Not needed, this never changes
                validate_non_coinbase_transaction_in_coinstate(
                    transaction, self.coinstate.current_chain_hash, self.coinstate)

                # Not needed either, this never becomes True if it was once False
                # validate_no_duplicate_output_references_in_transactions(self.transaction_pool + [transaction])
                return True
            except ValidateTransactionError:
                return False

        self.transaction_pool = [t for t in self.transaction_pool if is_valid(t)]

    def get_get_blocks_message(self) -> Tuple[GetBlocksMessage, int]:

        coinstate = self.coinstate
        height = coinstate.head().height

        oldness = list([pow(2, x) for x in range(0, 22)])
        old_heights = [x for x in [height - o for o in oldness] if x >= 0]

        potential_start_hashes = [
            coinstate.current_chain_hash
        ] + coinstate.get_block_hashes_at_heights(old_heights)

        return GetBlocksMessage(potential_start_hashes), height
