from __future__ import annotations
from skepticoin.networking.local_peer import DiskInterface
import traceback
from threading import Lock
from typing import Dict, List, Optional, Set, Tuple

from skepticoin.coinstate import CoinState
import random

from skepticoin.humans import human
from skepticoin.consensus import (
    validate_no_duplicate_output_references_in_transactions,
    validate_non_coinbase_transaction_by_itself,
    validate_non_coinbase_transaction_in_coinstate,
    ValidateTransactionError,
)
from .params import (
    MAX_IBD_PEERS,
    IBD_PEER_TIMEOUT,
    SWITCH_TO_ACTIVE_MODE_TIMEOUT,
    EMPTY_INVENTORY_BACKOFF,
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
            self.local_peer.disconnect(self.connected_peers[key], "duplicate")  # just drop the existing one

        self._sanity_check()
        self.connected_peers[key] = remote_peer
        if key in self.disconnected_peers:
            del self.disconnected_peers[key]
        self._sanity_check()

    def handle_peer_disconnected(self, remote_peer: ConnectedRemotePeer) -> None:
        self.local_peer.logger.info("%15s NetworkManager.handle_peer_disconnected()" % remote_peer.host)

        key = (remote_peer.host, remote_peer.port, remote_peer.direction)

        self._sanity_check()

        del self.connected_peers[key]

        if remote_peer.direction == OUTGOING:
            if not remote_peer.hello_received:
                remote_peer.ban_score += 1
                self.local_peer.logger.info('%15s Disconnected without hello, ban_score=%d'
                                            % (remote_peer.host, remote_peer.ban_score))
                self.disk_interface.write_peers(self.connected_peers)

            self.disconnected_peers[key] = remote_peer.as_disconnected()

        self._sanity_check()

    def get_active_peers(self) -> List[ConnectedRemotePeer]:
        return [p for p in self.connected_peers.values() if p.hello_sent and p.hello_received]

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
        self.actively_fetching_blocks_from_peers: List[
            Tuple[int, ConnectedRemotePeer]
        ] = []
        self.started_at = current_time
        self.transaction_pool: List[Transaction] = []
        self.last_known_valid_coinstate: Optional[CoinState] = None

    def step(self, current_time: int) -> None:
        if not self.should_actively_fetch_blocks(current_time):
            return  # no manual action required, blocks expected to be sent to us instead.

        ibd_candidates = [
            peer for peer in self.local_peer.network_manager.get_active_peers()
            if current_time > peer.last_empty_inventory_response_at + EMPTY_INVENTORY_BACKOFF
        ]

        if len(ibd_candidates) == 0:
            return

        # TODO note that if a peer disconnects, it is never removed from actively_fetching_blocks_from_peers, which
        # means that your IBD will be stuck until it times out. Not the best but it will recover eventually at least.
        self.actively_fetching_blocks_from_peers = [
            (timeout_at, p)
            for (timeout_at, p) in self.actively_fetching_blocks_from_peers
            if current_time < timeout_at and
            not inventory_batch_handled(p)]

        if len(self.actively_fetching_blocks_from_peers) > MAX_IBD_PEERS:
            return

        get_blocks_message = self.get_get_blocks_message()

        # TODO once MAX_IBD_PEERS > 1... pick one that you haven't picked before? potentially :-D
        remote_peer = random.choice(ibd_candidates)
        remote_peer.waiting_for_inventory = True
        self.actively_fetching_blocks_from_peers.append((current_time + IBD_PEER_TIMEOUT, remote_peer))
        remote_peer.send_message(get_blocks_message)

        # timeout is only implemented half-baked: it currently only limits when an new GetBlocksMessage will be sent;
        # but doesn't take the timed-out peer out of the loop that it's already in. This is not necessarily a bad thing.

    def should_actively_fetch_blocks(self, current_time: int) -> bool:

        return (
            (current_time > self.coinstate.head().timestamp + SWITCH_TO_ACTIVE_MODE_TIMEOUT)
            or (current_time <= self.started_at + 60)  # always sync w/ network right after restart
            or (current_time % 60 == 0)  # on average, every 1 minutes, do a network resync explicitly
        )

    def set_coinstate(self, coinstate: CoinState, validated: bool = True) -> None:
        with self.lock:
            self.local_peer.logger.info("%15s ChainManager.set_coinstate(%s)" % ("", coinstate))
            self.coinstate = coinstate
            self._cleanup_transaction_pool_for_coinstate(coinstate)
            if validated:
                self.last_known_valid_coinstate = coinstate

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

    def get_get_blocks_message(self) -> GetBlocksMessage:

        heights = get_recent_block_heights(self.coinstate.head().height)
        potential_start_hashes = [self.coinstate.by_height_at_head()[height].hash() for height in heights]
        return GetBlocksMessage(potential_start_hashes)


def get_recent_block_heights(block_height: int) -> List[int]:
    oldness = list(range(10)) + [pow(x, 2) for x in range(4, 64)]
    heights = [x for x in [block_height - o for o in oldness] if x >= 0]
    return heights
