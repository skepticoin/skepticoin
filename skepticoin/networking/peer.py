from datetime import datetime
import traceback
from io import BytesIO
import json
from ipaddress import IPv6Address
import random
from time import time
from threading import Lock

import struct
import socket
import selectors
import logging

from skepticoin.params import DESIRED_BLOCK_TIMESPAN
from ..utils import calc_work
from ..humans import human
from ..consensus import (
    validate_no_duplicate_output_references_in_transactions,
    validate_non_coinbase_transaction_by_itself,
    validate_non_coinbase_transaction_in_coinstate,
    ValidateTransactionError,
)
from .params import (
    TIME_BETWEEN_CONNECTION_ATTEMPTS,
    PORT,
    MAX_MESSAGE_SIZE,
    MAX_IBD_PEERS,
    IBD_PEER_TIMEOUT,
    GET_BLOCKS_INVENTORY_SIZE,
    GET_PEERS_INTERVAL,
    SWITCH_TO_ACTIVE_MODE_TIMEOUT,
    EMPTY_INVENTORY_BACKOFF,
)
from .messages import (
    SupportedVersion,
    MessageHeader,
    Message,
    Peer,
    PeersMessage,
    HelloMessage,
    GetBlocksMessage,
    GetDataMessage,
    GetPeersMessage,
    DataMessage,
    DATA_BLOCK,
    DATA_TRANSACTION,
    InventoryMessage,
    InventoryItem,
)
from .utils import get_recent_block_heights
from ..utils import block_filename
from ..__version__ import __version__


LISTENING_SOCKET = "LISTENING_SOCKET"
IRRELEVANT = "IRRELEVANT"
MAGIC = b'MAJI'

INCOMING = "INCOMING"
OUTGOING = "OUTGOING"


def _new_context():
    # just a random number will do; this is used for debugging only.
    return random.randrange(1 << 64)


class Manager:
    def step(self, current_time):
        raise NotImplementedError


class NetworkManager(Manager):

    def __init__(self, local_peer):
        self.local_peer = local_peer
        self.my_addresses = set()
        self.connected_peers = {}
        self.disconnected_peers = {}

    def _sanity_check(self):
        for key in self.disconnected_peers:
            if key in self.connected_peers:
                raise Exception("this shouldn't happen %s" % (key,))

    def step(self, current_time):
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

    def handle_peer_connected(self, remote_peer):
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

    def handle_peer_disconnected(self, remote_peer):
        self.local_peer.logger.info("%15s NetworkManager.handle_peer_disconnected()" % remote_peer.host)

        key = (remote_peer.host, remote_peer.port, remote_peer.direction)

        self._sanity_check()
        if remote_peer.direction == OUTGOING:
            self.disconnected_peers[key] = remote_peer
        del self.connected_peers[key]
        self._sanity_check()

    def get_active_peers(self):
        return [p for p in self.connected_peers.values() if p.hello_sent and p.hello_received]

    def broadcast_block(self, block):
        self.local_peer.logger.info("%15s ChainManager.broadcast_block(%s)" % ("", human(block.hash())))
        self.broadcast_message(DataMessage(DATA_BLOCK, block))

    def broadcast_transaction(self, transaction):
        self.broadcast_message(DataMessage(DATA_TRANSACTION, transaction))

    def broadcast_message(self, message):
        for peer in self.get_active_peers():
            try:
                # try/except b/c .send_message might try to set the selector for a just-closed sock to writing
                peer.send_message(message)
            except (OSError, ValueError, KeyError) as e:
                # OSError: e.g. ConnectionRefusedError, "Bad file descriptor"
                # ValueError, KeyError seen in the wild for selector problems; should be more exactly matched though
                self.local_peer.logger.info("%15s ChainManager.broadcast_message error %s" % (peer.host, e))


def inventory_batch_handled(peer):
    """Has the full loop GetBlocks -> Inventory -> GetData (n times) -> Data (n times) been completed?"""
    return not peer.waiting_for_inventory and peer.inventory_messages == []


class ChainManager(Manager):

    def __init__(self, local_peer, current_time):
        self.local_peer = local_peer
        self.lock = Lock()
        self.coinstate = None
        self.actively_fetching_blocks_from_peers = []
        self.started_at = current_time
        self.transaction_pool = []

    def step(self, current_time):
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

    def should_actively_fetch_blocks(self, current_time):
        return (
            (current_time > self.coinstate.head().timestamp + SWITCH_TO_ACTIVE_MODE_TIMEOUT)
            or (current_time <= self.started_at + 60)  # always sync w/ network right after restart
            or (current_time % 60 == 0)  # on average, every 1 minutes, do a network resync explicitly
        )

    def set_coinstate(self, coinstate):
        with self.lock:
            self.local_peer.logger.info("%15s ChainManager.set_coinstate(%s)" % ("", coinstate))
            self.coinstate = coinstate
            self._cleanup_transaction_pool_for_coinstate(coinstate)

    def add_transaction_to_pool(self, transaction):
        with self.lock:
            self.local_peer.logger.info(
                "%15s ChainManager.add_transaction_to_pool(%s)" % ("", human(transaction.hash())))

            try:
                validate_non_coinbase_transaction_by_itself(transaction)
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

    def get_state(self):
        with self.lock:
            return self.coinstate, self.transaction_pool

    def _cleanup_transaction_pool_for_coinstate(self, coinstate):
        # This is really the simplest (though not most efficient mechanism): simply remove now-invalid transactions from
        # the pool
        def is_valid(transaction):
            try:
                # validate_non_coinbase_transaction_by_itself(transaction) Not needed, this never changes
                validate_non_coinbase_transaction_in_coinstate(
                    transaction, self.coinstate.current_chain_hash, self.coinstate)

                # Not needed either, this never becomes True if it was once False
                # validate_no_duplicate_output_references_in_transactions(self.transaction_pool + [transaction])
                return True
            except ValidateTransactionError:
                return False

        self.transaction_pool = [t for t in self.transaction_pool if is_valid(t)]

    def get_get_blocks_message(self):
        heights = get_recent_block_heights(self.coinstate.head().height)
        potential_start_hashes = [self.coinstate.by_height_at_head()[height].hash() for height in heights]
        return GetBlocksMessage(potential_start_hashes)


class RemotePeer:
    def __init__(self, host, port, direction, last_connection_attempt):
        self.host = host
        self.port = port
        self.direction = direction

        self.last_connection_attempt = last_connection_attempt


class DisconnectedRemotePeer(RemotePeer):
    def __init__(self, host, port, direction, last_connection_attempt):
        super().__init__(host, port, direction, last_connection_attempt)

        # self.last_seen_alive = None

    def is_time_to_connect(self, current_time):
        return ((self.last_connection_attempt is None) or
                (current_time - self.last_connection_attempt >= TIME_BETWEEN_CONNECTION_ATTEMPTS))

    def as_connected(self, local_peer, sock):
        return ConnectedRemotePeer(local_peer, self.host, self.port, self.direction, self.last_connection_attempt, sock)


class MessageReceiver:
    def __init__(self, peer):
        self.peer = peer

        self.buffer = b''
        self.magic_read = False
        self.len = None

    def receive(self, data):
        self.buffer += data

        if not self.magic_read and len(self.buffer) >= 4:
            magic = self.buffer[:4]
            if magic != MAGIC:
                raise Exception("Insufficient magic")
            else:
                self.magic_read = True

            self.buffer = self.buffer[4:]

        if self.len is None and len(self.buffer) >= 4:
            (self.len,) = struct.unpack(b">I", self.buffer[:4])

            if self.len > MAX_MESSAGE_SIZE:
                raise Exception("len > MAX_MESSAGE_SIZE")

            self.buffer = self.buffer[4:]

        if self.len is not None and self.len <= len(self.buffer):
            self.handle_message_data(self.buffer[:self.len])

            self.buffer = self.buffer[self.len:]
            self.magic_read = False
            self.len = None
            self.receive(b"")  # recurse to repeat (multiple messages could be received in a single socket read)

    def handle_message_data(self, message_data):
        f = BytesIO(message_data)
        header = MessageHeader.stream_deserialize(f)
        message = Message.stream_deserialize(f)
        self.peer.handle_message_received(header, message)


class InventoryMessageState:
    def __init__(self, header, message):
        self.header = header
        self.message = message
        self.index = 0
        self.actually_used = False


class ConnectedRemotePeer(RemotePeer):
    def __init__(self, local_peer, host, port, direction, last_connection_attempt, sock):
        super().__init__(host, port, direction, last_connection_attempt)
        self.local_peer = local_peer
        self.sock = sock
        self.direction = direction

        self.receiver = MessageReceiver(self)
        self.send_backlog = []
        self.send_buffer = b''

        self.hello_sent = False
        self.hello_received = False

        self.sent = b''
        self.received = b''

        self.waiting_for_inventory = False
        self.last_empty_inventory_response_at = 0
        self.inventory_messages = []

        self._next_msg_id = 0
        self.last_get_peers_sent_at = None
        self.waiting_for_peers = False

    def as_disconnected(self):
        return DisconnectedRemotePeer(self.host, self.port, self.direction, self.last_connection_attempt)

    def step(self, current_time):
        """The responsibility of this method: to send the HelloMessage and GetPeersMessage."""

        if not self.hello_sent:
            ipv4_mapped = IPv6Address("::FFFF:%s" % self.host)
            port_if_known = self.port if self.port is not IRRELEVANT else 0

            my_ip_address = IPv6Address("0::0")  # Unspecified
            my_port = self.local_peer.port if self.local_peer.port else 0

            hello_message = HelloMessage(
                [SupportedVersion(0)], ipv4_mapped, port_if_known, my_ip_address, my_port, self.local_peer.nonce,
                b"sashimi " + __version__.encode("utf-8"))

            self.hello_sent = True
            self.send_message(hello_message)

        if not self.hello_received:
            return

        if ((self.last_get_peers_sent_at is None or current_time > self.last_get_peers_sent_at + GET_PEERS_INTERVAL)
                and not self.waiting_for_peers):

            self.send_message(GetPeersMessage())
            self.waiting_for_peers = True
            self.last_get_peers_sent_at = current_time

    def _get_msg_id(self):
        self._next_msg_id += 1
        return self._next_msg_id  # 1 is the first message id (0 being reserved for "unknown"). Dijkstra's dead.

    def send_message(self, message, prev_header=None):
        if prev_header is None:
            in_response_to, context = 0, _new_context()
        else:
            in_response_to, context = prev_header.id, prev_header.context
        header = MessageHeader(int(time()), self._get_msg_id(), in_response_to=in_response_to, context=context)

        self.local_peer.logger.info(
            "%15s ConnectedRemotePeer.send_message(%s %s)" % (self.host, type(message).__name__, header.format()))

        data = header.serialize() + message.serialize()
        self.send_backlog.append((MAGIC + struct.pack(b">I", len(data)) + data))

        self.check_message_backlog()

    def check_message_backlog(self):
        if len(self.send_buffer) == 0 and len(self.send_backlog) > 0:
            self.send_buffer = self.send_backlog.pop(0)
            self.start_sending()

    def start_sending(self):
        self.local_peer.selector.modify(self.sock, selectors.EVENT_READ | selectors.EVENT_WRITE, data=self)

    def stop_sending(self):
        self.local_peer.selector.modify(self.sock, selectors.EVENT_READ, data=self)

    def handle_message_received(self, header, message):
        self.local_peer.logger.info("%15s ConnectedRemotePeer.handle_message_received(%s %s)" % (
            self.host, type(message).__name__, header.format()))

        if isinstance(message, HelloMessage):
            return self.handle_hello_message_received(header, message)

        if not self.hello_received:
            raise Exception("First message must be Hello")

        if isinstance(message, GetBlocksMessage):
            return self.handle_get_blocks_message_received(header, message)

        if isinstance(message, InventoryMessage):
            return self.handle_inventory_message_received(header, message)

        if isinstance(message, GetDataMessage):
            return self.handle_get_data_message_received(header, message)

        if isinstance(message, DataMessage):
            return self.handle_data_message_received(header, message)

        if isinstance(message, GetPeersMessage):
            return self.handle_get_peers_message_received(header, message)

        if isinstance(message, PeersMessage):
            return self.handle_peers_message_received(header, message)

        raise NotImplementedError("%s" % message)

    def handle_can_send(self, sock):
        self.local_peer.logger.info("ConnectedRemotePeer.handle_can_send()")

        sent = sock.send(self.send_buffer)
        self.sent += self.send_buffer[:sent]
        self.send_buffer = self.send_buffer[sent:]

        if len(self.send_buffer) == 0:
            self.stop_sending()  # in principle: wasteful, but easy to reason about.
            self.check_message_backlog()

    def handle_receive_data(self, data):
        self.local_peer.logger.info("%15s ConnectedRemotePeer.handle_receive_data()" % self.host)
        self.received += data

        self.receiver.receive(data)

    def handle_hello_message_received(self, header, message):
        self.local_peer.logger.info(
            "%15s ConnectedRemotePeer.handle_hello_message_received(%s)" % (self.host, message.user_agent))
        self.hello_received = True

        if self.direction == INCOMING:
            # also add the peer to the list of disconnected_peers in reverse direction
            # TODO at some point: this means that if possible, each peer will be connected to twice. We should drop
            # connection if that happens. Probably like so: it's the prober that receives "hello" and then closes
            # because satisifed.
            key = (self.host, message.my_port, OUTGOING)
            nm = self.local_peer.network_manager
            nm._sanity_check()
            if key not in nm.disconnected_peers and key not in nm.connected_peers:
                nm.disconnected_peers[key] = DisconnectedRemotePeer(self.host, message.my_port, OUTGOING, None)
            nm._sanity_check()

        if self.direction == OUTGOING and message.nonce == self.local_peer.nonce:
            self.local_peer.network_manager.my_addresses.add((self.host, self.port))
            self.local_peer.disconnect(self, "connection to self")

        self.local_peer.disk_interface.update_peer_db(self)

    def handle_get_blocks_message_received(self, header, message):
        self.local_peer.logger.info("%15s ConnectedRemotePeer.handle_get_blocks_message_received()" % self.host)
        coinstate = self.local_peer.chain_manager.coinstate
        self.local_peer.logger.debug("%15s ... at coinstate %s" % (self.host, coinstate))
        for potential_start_hash in message.potential_start_hashes:
            self.local_peer.logger.debug("%15s ... psh %s" % (self.host, human(potential_start_hash)))
            if potential_start_hash in coinstate.block_by_hash:
                start_height = coinstate.block_by_hash[potential_start_hash].height + 1  # + 1: sent hash is last known
                if start_height not in coinstate.by_height_at_head():
                    # we have no new info
                    self.local_peer.logger.debug("%15s ... no new info" % self.host)
                    self.send_message(InventoryMessage([]), prev_header=header)
                    return

                if coinstate.by_height_at_head()[start_height].previous_block_hash == potential_start_hash:
                    # this final if checks that this particular potential_start_hash is on our active chain
                    break
        else:  # no break
            start_height = 1  # genesis is last known

        max_height = coinstate.head().height + 1  # + 1: range is exclusive, but we need to send this last block also
        items = [
            InventoryItem(DATA_BLOCK, coinstate.by_height_at_head()[height].hash())
            for height in range(start_height, min(start_height + GET_BLOCKS_INVENTORY_SIZE, max_height))
        ]
        self.local_peer.logger.debug("%15s ... returning from %s, %s items" % (self.host, start_height, len(items)))
        self.send_message(InventoryMessage(items), prev_header=header)

    def handle_inventory_message_received(self, header, message):
        self.local_peer.logger.info(
            "%15s ConnectedRemotePeer.handle_inventory_message_received(%s)" % (self.host, len(message.items)))
        if len(message.items) > 0:
            self.local_peer.logger.info(
                "%15s %s .. %s" % (self.host, human(message.items[0].hash), human(message.items[-1].hash)))

        if len(message.items) > GET_BLOCKS_INVENTORY_SIZE:
            raise Exception("Inventory msg too big")

        self.waiting_for_inventory = False

        if message.items == []:
            self.local_peer.logger.info("%15s ConnectedRemotePeer.last_empty_inventory_response_at set" % self.host)
            self.last_empty_inventory_response_at = int(time())  # TODO time() as a pass-along?
            return

        self.inventory_messages.append(InventoryMessageState(header, message))
        self.check_inventory_messages()

    def _get_hash_from_inventory_messages(self):
        while self.inventory_messages:
            msg_state = self.inventory_messages[0]

            if msg_state.index <= len(msg_state.message.items) - 1:
                if msg_state.message.items[msg_state.index].data_type != DATA_BLOCK:
                    raise Exception("We only deal w/ Block InventoryMessage for now")

                result = msg_state.message.items[msg_state.index].hash
                msg_state.index += 1
                return msg_state, result

            if not msg_state.actually_used and len(msg_state.message.items) > 0:
                self.local_peer.logger.info(
                    "%15s ConnectedRemotePeer._get_hash_from_inventory_messages: try again from %s" % (
                        self.host, human(msg_state.message.items[-1].hash)))

                get_blocks_message = GetBlocksMessage([msg_state.message.items[-1].hash])
                self.waiting_for_inventory = True
                # TODO consider adding something like the below
                # self.actively_fetching_blocks_from_peers.append((current_time + IBD_PEER_TIMEOUT, remote_peer))
                self.send_message(get_blocks_message, prev_header=msg_state.header)

            self.inventory_messages.pop(0)

        return None, None

    def check_inventory_messages(self):
        coinstate = self.local_peer.chain_manager.coinstate

        msg_state, next_hash = self._get_hash_from_inventory_messages()
        while next_hash is not None and next_hash in coinstate.block_by_hash:
            msg_state, next_hash = self._get_hash_from_inventory_messages()

        if next_hash is None or next_hash in coinstate.block_by_hash:
            return

        msg_state.actually_used = True
        self.send_message(GetDataMessage(DATA_BLOCK, next_hash), prev_header=msg_state.header)

    def handle_get_data_message_received(self, header, get_data_message):
        if get_data_message.data_type != DATA_BLOCK:
            raise NotImplementedError("We can only deal w/ DATA_BLOCK GetDataMessage objects for now")

        coinstate = self.local_peer.chain_manager.coinstate
        if get_data_message.hash not in coinstate.block_by_hash:
            # we simply silently ignore GetDataMessage for hashes we don't have... future work: inc banscore, or ...
            self.local_peer.logger.debug("%15s ConnectedRemotePeer.handle_data_message_received for unknown hash %s" % (
                self.host, human(get_data_message.hash)))
            return

        data_message = DataMessage(DATA_BLOCK, coinstate.block_by_hash[get_data_message.hash])

        self.local_peer.logger.debug("%15s ConnectedRemotePeer.handle_data_message_received for hash %s h. %s" % (
            self.host, human(get_data_message.hash), coinstate.block_by_hash[get_data_message.hash].height))
        self.send_message(data_message, prev_header=header)

    def handle_data_message_received(self, header, message):
        self.local_peer.logger.info("%15s ConnectedRemotePeer.handle_data_message_received(%s %s)" % (
            self.host, message.data_type, header.format()))

        if message.data_type == DATA_BLOCK:
            return self.handle_block_received(header, message)

        if message.data_type == DATA_TRANSACTION:
            return self.handle_transaction_received(header, message)

        raise NotImplementedError("Unknown DataMessage objects for now")

    def handle_block_received(self, header, message):
        # TODO deal with out-of-order blocks more gracefully

        block = message.data
        coinstate = self.local_peer.chain_manager.coinstate

        if block.hash() in coinstate.block_by_hash:
            # implicit here: when you receive a datamessage, this could be because you requested it; and thus you'll
            # want to request the next one (the below check does nothing if there's nothing to do)
            self.check_inventory_messages()

            self.local_peer.logger.debug("%15s ConnectedRemotePeer.handle_block_received() for known block %s" % (
                self.host, human(block.hash())))

            # Known block, just return
            return

        try:
            coinstate = coinstate.add_block(block, int(time()))  # TODO time() as a pass-along?
            self.local_peer.chain_manager.set_coinstate(coinstate)
            self.local_peer.disk_interface.save_block(block)

        except Exception as e:
            # TODO: dirty hack at this particular point... to allow for out-of-order blocks to not take down the whole
            # peer, but this should more specifically match for a short list of OK problems.
            self.local_peer.logger.info("%15s INVALID block %s" % (self.host, str(e)))

        # implicit here: when you receive a datamessage, this is because you requested it; and thus you'll want to
        # request the next one
        self.check_inventory_messages()

        if block == coinstate.head() and header.in_response_to == 0:
            # "header.in_response_to == 0" is being used as a bit of a proxy for "not in IBD" here, but it would be
            # better to check for that state more explicitly. We don't want to broadcast blocks while in IBD, because in
            # that state the fact that some block is our new head doesn't mean at all that we're talking about the real
            # chain's new head, and only the latter is relevant to the rest of the world.
            self.local_peer.network_manager.broadcast_block(block)

    def handle_transaction_received(self, header, message):
        transaction = message.data
        if transaction in self.local_peer.chain_manager.transaction_pool:
            return

        if self.local_peer.chain_manager.add_transaction_to_pool(transaction):
            # if this is valid and new... just broadcast it to every peer you know. I'm sure this is inefficient, but
            # at least peers will stop broadcasting once they receive it a second time themselves.
            self.local_peer.network_manager.broadcast_transaction(transaction)

    def handle_get_peers_message_received(self, header, message):
        peers = []

        for peer in self.local_peer.network_manager.connected_peers.values():
            if peer.direction == OUTGOING:
                peers.append(Peer(int(time()), IPv6Address("::FFFF:%s" % peer.host), peer.port))

        for peer in self.local_peer.network_manager.disconnected_peers.values():
            if peer.direction == OUTGOING:
                peers.append(Peer(0, IPv6Address("::FFFF:%s" % peer.host), peer.port))  # TODO 'last seen' time.

        # TODO filter out local network addresses (also on the receiving end)
        peers = peers[:1000]  # send 1000 peers max.

        self.send_message(PeersMessage(peers), prev_header=header)

    def handle_peers_message_received(self, header, message):
        # TODO peers that have been communicated to you like this should be marked as "not checked yet" somehow, to
        # avoid being flooded with nonsense peers.

        self.waiting_for_peers = False

        for announced_peer in message.peers:
            ipv4_mapped = announced_peer.ip_address.ipv4_mapped
            if ipv4_mapped is None:
                continue  # IPv6? Ain't nobody got time for that! (Seriously though, the protocol supports it if needed)
            host = ipv4_mapped.exploded

            # TODO factor out copypasta
            key = (host, announced_peer.port, OUTGOING)
            nm = self.local_peer.network_manager
            nm._sanity_check()
            if key not in nm.disconnected_peers and key not in nm.connected_peers:
                nm.disconnected_peers[key] = DisconnectedRemotePeer(host, announced_peer.port, OUTGOING, None)
            nm._sanity_check()


class DiskInterface:
    """Catch-all for writing to and reading from disk, factored out to facilitate testing."""

    def save_block(self, block):
        with open('chain/%s' % block_filename(block), 'wb') as f:
            f.write(block.serialize())

    def update_peer_db(self, remote_peer):
        if remote_peer.direction != OUTGOING:
            return

        # TSTTCPW... really quite barebones like this :-D
        db = [tuple(li) for li in json.loads(open("peers.json").read())]

        tup = (remote_peer.host, remote_peer.port, remote_peer.direction)
        if tup not in db:
            db.append(tup)

        with open("peers.json", "w") as f:
            json.dump(db, f, indent=4)

    def save_transaction_for_debugging(self, transaction):
        with open("/tmp/%s.transaction" % human(transaction.hash()), 'wb') as f:
            f.write(transaction.serialize())


class LocalPeer:

    def __init__(self, disk_interface=DiskInterface()):
        self.disk_interface = disk_interface
        self.port = None  # perhaps just push this into the signature here?
        self.nonce = random.randrange(pow(2, 32))
        self.selector = selectors.DefaultSelector()
        self.network_manager = NetworkManager(self)
        self.chain_manager = ChainManager(self, int(time()))
        self.managers = [
            self.network_manager,
            self.chain_manager,
        ]

        self.logger = logging.getLogger("skepticoin.networking.%s" % self.nonce)

    def start_listening(self, port=PORT):
        self.port = port
        self.logger.info("%15s LocalPeer.start_listening(%s)" % ("", port))
        lsock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        # https://stackoverflow.com/questions/4465959/python-errno-98-address-already-in-use/4466035#4466035
        lsock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        lsock.bind(("", port))
        lsock.listen()
        lsock.setblocking(False)
        self.selector.register(lsock, selectors.EVENT_READ, data=LISTENING_SOCKET)

    def handle_incoming_connection(self, sock):
        self.logger.info("%15s LocalPeer.handle_incoming_connection()" % "")
        # TODO only accept a single (incoming, outgoing) connection from each peer
        conn, addr = sock.accept()
        conn.setblocking(False)
        events = selectors.EVENT_READ

        remote_host = conn.getpeername()[0]
        remote_port = conn.getpeername()[1]
        remote_peer = ConnectedRemotePeer(self, remote_host, remote_port, INCOMING, None, conn)
        self.selector.register(conn, events, data=remote_peer)
        self.network_manager.handle_peer_connected(remote_peer)

    def handle_remote_peer_selector_event(self, key, mask):
        # self.logger.info("LocalPeer.handle_remote_peer_selector_event()")

        sock = key.fileobj
        remote_peer = key.data
        assert isinstance(remote_peer, ConnectedRemotePeer)

        try:
            if mask & selectors.EVENT_READ:
                recv_data = sock.recv(1024)

                if recv_data:
                    remote_peer.handle_receive_data(recv_data)
                else:
                    self.disconnect(remote_peer, "connection closed remotely")  # is this so?

            if mask & selectors.EVENT_WRITE:
                remote_peer.handle_can_send(sock)

        except OSError as e:  # e.g. ConnectionRefusedError, "Bad file descriptor"
            # no print-to-screen for this one
            self.logger.info("%15s Disconnecting remote peer %s" % (remote_peer.host, e))
            self.disconnect(remote_peer, "OS error")

        except ValueError as e:  # e.g. Invalid file descriptor: {}".format(fd)) ... more exact matching is better tho
            # no print-to-screen for this one
            self.logger.info("%15s Disconnecting remote peer %s" % (remote_peer.host, e))
            self.disconnect(remote_peer, "OS error")

        except Exception as e:
            # We take the position that any exception caused is reason to disconnect. This allows the code that talks to
            # peers to not have special cases for exceptions since they will all be caught by this catch-all.
            self.logger.info("%15s Disconnecting remote peer %s" % (remote_peer.host, e))
            self.logger.warning(traceback.format_exc())  # be loud... this is likely a programming error.

            self.disconnect(remote_peer, "Exception")

    def disconnect(self, remote_peer, reason=""):
        self.logger.info("%15s LocalPeer.disconnect(%s)" % (remote_peer.host, reason))

        try:
            self.selector.unregister(remote_peer.sock)
            remote_peer.sock.close()
            self.network_manager.handle_peer_disconnected(remote_peer.as_disconnected())
        except Exception as e:
            # yes yes... sweeping things under the carpet here. until I actually RTFM and think this through
            # (i.e. the whole business of unregistering things that are already in some half-baked state)
            # at least one path how you might end up here: a EVENT_WRITE is reached for a socket that was just closed
            # as a consequence of something that was read.
            self.logger.info("%15s Error while disconnecting %s" % ("", e))

    def start_outgoing_connection(self, disconnected_peer):
        self.logger.info("%15s LocalPeer.start_outgoing_connection()" % disconnected_peer.host)

        server_addr = (disconnected_peer.host, disconnected_peer.port)

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setblocking(False)
        sock.connect_ex(server_addr)
        events = selectors.EVENT_READ

        remote_peer = disconnected_peer.as_connected(self, sock)
        self.selector.register(sock, events, data=remote_peer)
        self.network_manager.handle_peer_connected(remote_peer)

    def step_managers(self, current_time):
        for manager in self.managers:
            if not self.running:
                break

            manager.step(current_time)

    def handle_selector_events(self):
        events = self.selector.select(timeout=1)  # TODO this is for the managers to do something... tune it though
        for key, mask in events:
            if not self.running:
                break

            if key.data is LISTENING_SOCKET:
                self.handle_incoming_connection(key.fileobj)
            else:
                self.handle_remote_peer_selector_event(key, mask)

    def run(self):
        self.running = True
        try:
            while self.running:
                current_time = int(time())
                self.step_managers(current_time)
                self.handle_selector_events()
        except Exception:
            self.logger.error("Uncaught exception in LocalPeer.run()")
            self.logger.error(traceback.format_exc())
        finally:
            self.logger.info("%15s LocalPeer selector close" % "")
            self.selector.close()
            self.logger.info("%15s LocalPeer selector closed" % "")

    def stop(self):
        self.logger.info("%15s LocalPeer.stop()" % "")
        self.running = False

    def show_stats(self):
        coinstate = self.chain_manager.coinstate

        print("NETWORK")
        print("Nr. of connected peers:", len(self.network_manager.get_active_peers()))
        for p in self.network_manager.get_active_peers()[:10]:
            print("%15s:%s - %s" % (p.host, p.port if p.port != IRRELEVANT else "....", p.direction))

        print("\nCHAIN")
        for (head, lca) in coinstate.forks():
            if head.height < coinstate.head().height - 10:
                continue  # don't show forks which are out-ran by more than 10 blocks

            print("Height    %s" % head.height)
            print("Date/time %s" % datetime.fromtimestamp(head.timestamp).isoformat())
            if head.height != lca.height:
                print("diverges for %s blocks" % (head.height - lca.height))
            print()

    def show_network_stats(self):
        print("NETWORK")
        print("Nr. of connected peers:", len(self.network_manager.get_active_peers()))
        print("Nr. of unique hosts   :", len(set(p.host for p in self.network_manager.get_active_peers())))
        print("Nr. of listening hosts:",
              len([p for p in self.network_manager.get_active_peers() if p.direction == OUTGOING]))

        per_host = {}

        for p in self.network_manager.get_active_peers():
            if p.host not in per_host:
                per_host[p.host] = (0, 0)

            incoming, outgoing = per_host[p.host]
            if p.direction == INCOMING:
                per_host[p.host] = incoming + 1, outgoing
            else:
                per_host[p.host] = incoming, outgoing + 1

        print("\ndetails:")
        for host, (incoming, outgoing) in per_host.items():
            print("%15s: %2d incoming, %2d outgoing" % (host, incoming, outgoing))

    def show_chain_stats(self):
        coinstate = self.chain_manager.coinstate

        def get_block_timespan_factor(n):
            # Current block duration over past n block as a factor of DESIRED_BLOCK_TIMESPAN, e.g. 0.5 for twice desired
            # speed
            diff = coinstate.head().timestamp - coinstate.at_head.block_by_height[coinstate.head().height - n].timestamp
            return diff / (DESIRED_BLOCK_TIMESPAN * n)

        def get_network_hash_rate(n):
            total_over_blocks = sum(
                calc_work(coinstate.at_head.block_by_height[coinstate.head().height - i].target) for i in range(n))

            diff = coinstate.head().timestamp - coinstate.at_head.block_by_height[coinstate.head().height - n].timestamp

            return total_over_blocks / diff

        print("WASTELAND STATS")
        print("Current target: ", human(coinstate.head().target))
        print("Current work:   ", calc_work(coinstate.head().target))
        print("Timespan factor:", get_block_timespan_factor(100))
        print("Hash rate:      ", get_network_hash_rate(100))
