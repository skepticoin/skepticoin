from __future__ import annotations
from io import BytesIO

from ipaddress import IPv6Address

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from skepticoin.networking.local_peer import LocalPeer

from time import time
from typing import Dict, List, Optional, Tuple

import struct
import socket
import selectors

from skepticoin.humans import human
from .params import (
    GET_BLOCKS_INVENTORY_SIZE,
    GET_PEERS_INTERVAL,
    TIME_BETWEEN_CONNECTION_ATTEMPTS,
)
from skepticoin.datatypes import Block, Transaction
from skepticoin.networking.params import MAX_MESSAGE_SIZE
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
import json
from skepticoin.__version__ import __version__
import random


LISTENING_SOCKET = "LISTENING_SOCKET"
IRRELEVANT = "IRRELEVANT"  # TODO don't use a string for a port number
MAGIC = b'MAJI'

INCOMING = "INCOMING"
OUTGOING = "OUTGOING"


def load_peers_from_list(
    lst: List[Tuple[str, int, str]]
) -> Dict[Tuple[str, int, str], DisconnectedRemotePeer]:

    return {
        (host, port, direction): DisconnectedRemotePeer(host, port, direction, None)
        for (host, port, direction) in lst
    }


def load_peers() -> Dict[Tuple[str, int, str], DisconnectedRemotePeer]:
    try:
        db = [tuple(li) for li in json.loads(open("peers.json").read())]
    except Exception:
        db = []

    return load_peers_from_list(db)  # type: ignore


def _new_context() -> int:
    # just a random number will do; this is used for debugging only.
    return random.randrange(1 << 64)


class InventoryMessageState:
    def __init__(self, header: MessageHeader, message: InventoryMessage):
        self.header = header
        self.message = message
        self.index = 0
        self.actually_used = False


class MessageReceiver:
    def __init__(self, peer: ConnectedRemotePeer):
        self.peer = peer

        self.buffer = b''
        self.magic_read = False
        self.len = None

    def receive(self, data: bytes) -> None:
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

            if self.len > MAX_MESSAGE_SIZE:  # type: ignore
                raise Exception("len > MAX_MESSAGE_SIZE")

            self.buffer = self.buffer[4:]

        if self.len is not None and self.len <= len(self.buffer):
            self.handle_message_data(self.buffer[:self.len])

            self.buffer = self.buffer[self.len:]
            self.magic_read = False
            self.len = None
            self.receive(b"")  # recurse to repeat (multiple messages could be received in a single socket read)

    def handle_message_data(self, message_data: bytes) -> None:
        f = BytesIO(message_data)
        header = MessageHeader.stream_deserialize(f)
        message = Message.stream_deserialize(f)
        self.peer.handle_message_received(header, message)


class RemotePeer:
    def __init__(
        self,
        host: str,
        port: int,
        direction: str,
        last_connection_attempt: Optional[int],
    ):
        self.host = host
        self.port = port
        self.direction = direction

        self.last_connection_attempt = last_connection_attempt


class DisconnectedRemotePeer(RemotePeer):
    def __init__(
        self,
        host: str,
        port: int,
        direction: str,
        last_connection_attempt: Optional[int],
    ):
        super().__init__(host, port, direction, last_connection_attempt)

        # self.last_seen_alive = None

    def is_time_to_connect(self, current_time: int) -> bool:
        return ((self.last_connection_attempt is None) or
                (current_time - self.last_connection_attempt >= TIME_BETWEEN_CONNECTION_ATTEMPTS))

    def as_connected(self, local_peer: LocalPeer, sock: socket.socket) -> ConnectedRemotePeer:
        return ConnectedRemotePeer(local_peer, self.host, self.port, self.direction, self.last_connection_attempt, sock)


class ConnectedRemotePeer(RemotePeer):
    def __init__(
        self,
        local_peer: LocalPeer,
        host: str,
        port: int,
        direction: str,
        last_connection_attempt: Optional[int],
        sock: socket.socket,
    ):
        super().__init__(host, port, direction, last_connection_attempt)
        self.local_peer = local_peer
        self.sock = sock
        self.direction = direction

        self.receiver = MessageReceiver(self)
        self.send_backlog: List[bytes] = []
        self.send_buffer: bytes = b""

        self.hello_sent: bool = False
        self.hello_received: bool = False

        self.waiting_for_inventory: bool = False
        self.last_empty_inventory_response_at: int = 0
        self.inventory_messages: List[InventoryMessageState] = []

        self._next_msg_id: int = 0
        self.last_get_peers_sent_at: Optional[int] = None
        self.waiting_for_peers: bool = False

    def as_disconnected(self) -> DisconnectedRemotePeer:
        return DisconnectedRemotePeer(self.host, self.port, self.direction, self.last_connection_attempt)

    def step(self, current_time: int) -> None:
        """The responsibility of this method: to send the HelloMessage and GetPeersMessage."""

        if not self.hello_sent:
            ipv4_mapped = IPv6Address("::FFFF:%s" % self.host)
            port_if_known = self.port if self.port is not IRRELEVANT else 0  # type: ignore

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

    def _get_msg_id(self) -> int:
        self._next_msg_id += 1
        return self._next_msg_id  # 1 is the first message id (0 being reserved for "unknown"). Dijkstra's dead.

    def send_message(
        self, message: Message, prev_header: Optional[MessageHeader] = None
    ) -> None:
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

    def check_message_backlog(self) -> None:
        if len(self.send_buffer) == 0 and len(self.send_backlog) > 0:
            self.send_buffer = self.send_backlog.pop(0)
            self.start_sending()

    def start_sending(self) -> None:
        try:
            self.local_peer.selector.modify(self.sock, selectors.EVENT_READ | selectors.EVENT_WRITE, data=self)
        except ValueError:
            self.local_peer.logger.error("%15s ConnectedRemotePeer.start_sending() ValueError" % (self.host))

    def stop_sending(self) -> None:
        self.local_peer.selector.modify(self.sock, selectors.EVENT_READ, data=self)

    def handle_message_received(self, header: MessageHeader, message: Message) -> None:
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

    def handle_can_send(self, sock: socket.socket) -> None:
        self.local_peer.logger.info("ConnectedRemotePeer.handle_can_send()")

        sent = sock.send(self.send_buffer)
        self.send_buffer = self.send_buffer[sent:]

        if len(self.send_buffer) == 0:
            self.stop_sending()  # in principle: wasteful, but easy to reason about.
            self.check_message_backlog()

    def handle_receive_data(self, data: bytes) -> None:
        self.local_peer.logger.info("%15s ConnectedRemotePeer.handle_receive_data()" % self.host)
        self.receiver.receive(data)

    def handle_hello_message_received(
        self, header: MessageHeader, message: HelloMessage
    ) -> None:
        self.local_peer.logger.info(
            "%15s ConnectedRemotePeer.handle_hello_message_received(%s)" % (self.host, str(message.user_agent)))
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

        self.local_peer.disk_interface.overwrite_peers(list(self.local_peer.network_manager.connected_peers.values()))

    def handle_get_blocks_message_received(self, header: MessageHeader, message: GetBlocksMessage) -> None:
        self.local_peer.logger.info("%15s ConnectedRemotePeer.handle_get_blocks_message_received()" % self.host)
        coinstate = self.local_peer.chain_manager.coinstate
        self.local_peer.logger.debug("%15s ... at coinstate %s" % (self.host, coinstate))
        for potential_start_hash in message.potential_start_hashes:
            self.local_peer.logger.debug("%15s ... psh %s" % (self.host, human(potential_start_hash)))
            assert coinstate
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
        assert coinstate
        max_height = coinstate.head().height + 1  # + 1: range is exclusive, but we need to send this last block also
        items = [
            InventoryItem(DATA_BLOCK, coinstate.by_height_at_head()[height].hash())
            for height in range(start_height, min(start_height + GET_BLOCKS_INVENTORY_SIZE, max_height))
        ]
        self.local_peer.logger.debug("%15s ... returning from %s, %s items" % (self.host, start_height, len(items)))
        self.send_message(InventoryMessage(items), prev_header=header)

    def handle_inventory_message_received(
        self, header: MessageHeader, message: InventoryMessage
    ) -> None:
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

    def _get_hash_from_inventory_messages(
        self,
    ) -> Tuple[Optional[InventoryMessageState], Optional[bytes]]:
        while self.inventory_messages:
            msg_state = self.inventory_messages[0]

            if msg_state.index <= len(msg_state.message.items) - 1:
                if msg_state.message.items[msg_state.index].data_type != DATA_BLOCK:
                    raise Exception("We only deal w/ Block InventoryMessage for now")

                result: bytes = msg_state.message.items[msg_state.index].hash
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

    def check_inventory_messages(self) -> None:
        coinstate = self.local_peer.chain_manager.coinstate
        assert coinstate

        msg_state, next_hash = self._get_hash_from_inventory_messages()
        while next_hash is not None and next_hash in coinstate.block_by_hash:
            msg_state, next_hash = self._get_hash_from_inventory_messages()

        if next_hash is None or next_hash in coinstate.block_by_hash:
            return

        assert msg_state
        msg_state.actually_used = True
        self.send_message(GetDataMessage(DATA_BLOCK, next_hash), prev_header=msg_state.header)

    def handle_get_data_message_received(
        self, header: MessageHeader, get_data_message: GetDataMessage
    ) -> None:
        if get_data_message.data_type != DATA_BLOCK:
            raise NotImplementedError("We can only deal w/ DATA_BLOCK GetDataMessage objects for now")

        coinstate = self.local_peer.chain_manager.coinstate
        assert coinstate

        if get_data_message.hash not in coinstate.block_by_hash:
            # we simply silently ignore GetDataMessage for hashes we don't have... future work: inc banscore, or ...
            self.local_peer.logger.debug("%15s ConnectedRemotePeer.handle_data_message_received for unknown hash %s" % (
                self.host, human(get_data_message.hash)))
            return

        data_message = DataMessage(DATA_BLOCK, coinstate.block_by_hash[get_data_message.hash])

        self.local_peer.logger.debug("%15s ConnectedRemotePeer.handle_data_message_received for hash %s h. %s" % (
            self.host, human(get_data_message.hash), coinstate.block_by_hash[get_data_message.hash].height))
        self.send_message(data_message, prev_header=header)

    def handle_data_message_received(self, header: MessageHeader, message: DataMessage) -> None:
        self.local_peer.logger.info("%15s ConnectedRemotePeer.handle_data_message_received(%s %s)" % (
            self.host, str(message.data_type), header.format()))

        if message.data_type == DATA_BLOCK:
            return self.handle_block_received(header, message)

        if message.data_type == DATA_TRANSACTION:
            return self.handle_transaction_received(header, message)

        raise NotImplementedError("Unknown DataMessage objects for now")

    def handle_block_received(
        self, header: MessageHeader, message: DataMessage
    ) -> None:
        # TODO deal with out-of-order blocks more gracefully

        block: Block = message.data  # type: ignore
        coinstate = self.local_peer.chain_manager.coinstate
        assert coinstate

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

    def handle_transaction_received(
        self, header: MessageHeader, message: DataMessage
    ) -> None:
        transaction: Transaction = message.data  # type: ignore
        if transaction in self.local_peer.chain_manager.transaction_pool:
            return

        if self.local_peer.chain_manager.add_transaction_to_pool(transaction):
            # if this is valid and new... just broadcast it to every peer you know. I'm sure this is inefficient, but
            # at least peers will stop broadcasting once they receive it a second time themselves.
            self.local_peer.network_manager.broadcast_transaction(transaction)

    def handle_get_peers_message_received(
        self, header: MessageHeader, message: GetPeersMessage
    ) -> None:
        peers: List[Peer] = []

        for con_peer in self.local_peer.network_manager.connected_peers.values():
            if con_peer.direction == OUTGOING:
                peers.append(Peer(int(time()), IPv6Address("::FFFF:%s" % con_peer.host), con_peer.port))

        for discon_peer in self.local_peer.network_manager.disconnected_peers.values():
            if discon_peer.direction == OUTGOING:
                peers.append(Peer(0, IPv6Address("::FFFF:%s" % discon_peer.host),
                             discon_peer.port))  # TODO 'last seen' time.

        # TODO filter out local network addresses (also on the receiving end)
        peers = peers[:1000]  # send 1000 peers max.

        self.send_message(PeersMessage(peers), prev_header=header)

    def handle_peers_message_received(
        self, header: MessageHeader, message: PeersMessage
    ) -> None:
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
