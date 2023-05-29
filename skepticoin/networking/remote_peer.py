from __future__ import annotations
from io import BytesIO
import logging

from ipaddress import IPv6Address
from typing import Dict, TYPE_CHECKING, Tuple

if TYPE_CHECKING:
    from skepticoin.networking.local_peer import LocalPeer

from time import time
from typing import List, Optional

import struct
import socket
import selectors

from skepticoin.humans import human
from .params import (
    GET_BLOCKS_INVENTORY_SIZE,
    GET_PEERS_INTERVAL,
    MAX_CONNECTION_ATTEMPTS,
    TIME_TO_SECOND_CONNECTION_ATTEMPT,
    MAX_TIME_BETWEEN_CONNECTION_ATTEMPTS,
)
from skepticoin.datatypes import Block, Transaction
from skepticoin.networking.params import MAX_MESSAGE_SIZE
from .messages import (
    DATATYPES,
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
        (host, port, direction): DisconnectedRemotePeer(host, port, direction, None, ban_score=0)
        for (host, port, direction) in lst
    }


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
        ban_score: int
    ):
        self.host = host
        self.port = port
        self.direction = direction
        self.last_connection_attempt = last_connection_attempt
        self.ban_score = ban_score


class DisconnectedRemotePeer(RemotePeer):
    def __init__(
        self,
        host: str,
        port: int,
        direction: str,
        last_connection_attempt: Optional[int],
        ban_score: int
    ):
        super().__init__(host, port, direction, last_connection_attempt, ban_score)

    def is_time_to_connect(self, current_time: int) -> bool:
        if self.ban_score > MAX_CONNECTION_ATTEMPTS:
            return False
        time_between = min(
            TIME_TO_SECOND_CONNECTION_ATTEMPT * pow(2, self.ban_score),
            MAX_TIME_BETWEEN_CONNECTION_ATTEMPTS)
        return ((self.last_connection_attempt is None) or
                (current_time - self.last_connection_attempt >= time_between))

    def as_connected(self, local_peer: LocalPeer, sock: socket.socket) -> ConnectedRemotePeer:
        return ConnectedRemotePeer(local_peer, self.host, self.port, self.direction, self.last_connection_attempt, sock,
                                   self.ban_score)


class ConnectedRemotePeer(RemotePeer):
    def __init__(
        self,
        local_peer: LocalPeer,
        host: str,
        port: int,
        direction: str,
        last_connection_attempt: Optional[int],
        sock: socket.socket,
        ban_score: int,
    ):
        super().__init__(host, port, direction, last_connection_attempt, ban_score)
        self.local_peer = local_peer
        self.sock = sock
        self.direction = direction
        self.connection_to_self = False

        self.receiver = MessageReceiver(self)
        self.send_backlog: List[bytes] = []
        self.send_buffer: bytes = b""

        self.hello_sent: bool = False
        self.hello_received: bool = False

        self.waiting_for_inventory: bool = False
        self.last_inventory_response_at: int = 0
        self.last_inventory_request_at: int = 0
        self.inventory_messages: List[InventoryMessageState] = []
        self.block_receive_buffer: List[Block] = []

        self._next_msg_id: int = 0
        self.last_get_peers_sent_at: Optional[int] = None
        self.waiting_for_peers: bool = False

        # informational trackers
        self.height_sent = 0
        self.height_received = 0
        self.last_message_received_at = 0

    def as_disconnected(self) -> DisconnectedRemotePeer:
        return DisconnectedRemotePeer(self.host, self.port, self.direction,
                                      self.last_connection_attempt, self.ban_score)

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

        if self.connection_to_self:
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

        data = header.serialize() + message.serialize()

        self.local_peer.logger.info(
            "%15s ConnectedRemotePeer.send_message(%s %s len=%d)"
            % (self.host, type(message).__name__, header.format(), len(data)))

        self.send_backlog.append((MAGIC + struct.pack(b">I", len(data)) + data))

        self.start_sending()

    def start_sending(self) -> None:
        try:
            self.local_peer.selector.modify(self.sock, selectors.EVENT_READ | selectors.EVENT_WRITE, data=self)
        except Exception as e:
            self.local_peer.logger.info(
                "%15s ConnectedRemotePeer.start_sending() Error: %s\n" % (self.host, str(e)))
            self.local_peer.disconnect(self, e)

    def stop_sending(self) -> None:
        self.local_peer.selector.modify(self.sock, selectors.EVENT_READ, data=self)

    def handle_message_received(self, header: MessageHeader, message: Message) -> None:
        self.local_peer.logger.info("%15s ConnectedRemotePeer.handle_message_received(%s %s)" % (
            self.host, type(message).__name__, header.format()))

        self.last_message_received_at = int(time())

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
        self.local_peer.logger.debug(
            "%15s ConnectedRemotePeer.handle_can_send(buffer=%d, backlog=%d)" % (
                self.host, len(self.send_buffer), len(self.send_backlog)))

        while True:
            if len(self.send_buffer) == 0:
                if len(self.send_backlog) == 0:
                    self.stop_sending()
                    return
                else:
                    self.send_buffer = self.send_backlog.pop(0)

            try:
                sent = sock.send(self.send_buffer)
                self.send_buffer = self.send_buffer[sent:]
            except BlockingIOError as e:
                self.local_peer.logger.debug("%15s ConnectedRemotePeer.handle_can_send(): %s" % (self.host, str(e)))
                return

    def handle_receive_data(self, data: bytes) -> None:
        self.local_peer.logger.debug("%15s ConnectedRemotePeer.handle_receive_data(%d)" % (self.host, len(data)))
        self.receiver.receive(data)

    def handle_hello_message_received(
        self, header: MessageHeader, message: HelloMessage
    ) -> None:
        self.local_peer.logger.info(
            "%15s ConnectedRemotePeer.handle_hello_message_received(%s)" % (self.host, str(message.user_agent)))
        self.hello_received = True
        self.ban_score = 0

        if self.direction == INCOMING:
            # also add the peer to the list of disconnected_peers in reverse direction
            # TODO at some point: this means that if possible, each peer will be connected to twice. We should drop
            # connection if that happens. Probably like so: it's the prober that receives "hello" and then closes
            # because satisifed.
            key = (self.host, message.my_port, OUTGOING)
            nm = self.local_peer.network_manager
            nm._sanity_check()
            if key in nm.disconnected_peers:
                # this is likely due to lack of a network return path, e.g. home Internet users without a DMZ
                self.local_peer.logger.info("%15s incoming with ban_score=%d" % (self.host, self.ban_score))
            elif key not in nm.connected_peers:
                nm.disconnected_peers[key] = DisconnectedRemotePeer(self.host, message.my_port, OUTGOING,
                                                                    last_connection_attempt=None, ban_score=0)
            nm._sanity_check()

        if self.direction == OUTGOING:
            self.local_peer.disk_interface.write_peers(self)

        if message.nonce == self.local_peer.nonce:
            self.local_peer.network_manager.my_addresses.add((self.host, self.port))
            self.connection_to_self = True

    def handle_get_blocks_message_received(self, header: MessageHeader, message: GetBlocksMessage) -> None:

        coinstate = self.local_peer.chain_manager.coinstate

        if self.local_peer.logger.isEnabledFor(logging.INFO):
            def hash_to_height(h: bytes) -> str:
                try:
                    return str(coinstate.get_block_by_hash(h).height)
                except KeyError:
                    return "Unknown:" + human(h)
            self.local_peer.logger.info(
                "%15s ConnectedRemotePeer.handle_get_blocks_message_received(heights=[%s]) ... at coinstate %s" % (
                    self.host, " ".join([hash_to_height(h) for h in message.potential_start_hashes]),
                    coinstate
                )
            )

        for potential_start_hash in message.potential_start_hashes:
            self.local_peer.logger.debug("%15s ... psh %s" % (self.host, human(potential_start_hash)))
            if coinstate.has_block_hash(potential_start_hash):
                start_height = coinstate.get_block_by_hash(
                    potential_start_hash
                ).height + 1  # + 1: sent hash is last known
                if start_height > coinstate.head().height:
                    # we have no new info
                    self.local_peer.logger.debug("%15s ... no new info" % self.host)
                    self.send_message(InventoryMessage([]), prev_header=header)
                    self.height_sent = coinstate.head().height
                    return

                if coinstate.block_by_height_at_head(start_height).previous_block_hash == potential_start_hash:
                    # this final if checks that this particular potential_start_hash is on our active chain
                    break
        else:  # no break
            start_height = 1  # genesis is last known
        max_height = coinstate.head().height + 1  # + 1: range is exclusive, but we need to send this last block also
        end_height = min(start_height + GET_BLOCKS_INVENTORY_SIZE, max_height)
        hashes = coinstate.get_block_hashes_at_heights(
            list(range(start_height, end_height))
        )

        items = [InventoryItem(DATA_BLOCK, hash) for hash in hashes]

        self.local_peer.logger.info("%15s ... returning inventory from start_height=%d, %d items"
                                    % (self.host, start_height, len(items)))
        self.send_message(InventoryMessage(items), prev_header=header)
        self.height_sent = end_height

    def handle_inventory_message_received(
        self, header: MessageHeader, message: InventoryMessage
    ) -> None:
        self.local_peer.logger.info(
            "%15s ConnectedRemotePeer.handle_inventory_message_received(len=%d from=%s to=%s)" % (
                self.host, len(message.items),
                human(message.items[0].hash) if len(message.items) > 0 else "None",
                human(message.items[-1].hash) if len(message.items) > 0 else "None"))

        self.last_inventory_response_at = int(time())  # TODO time() as a pass-along?

        coinstate = self.local_peer.chain_manager.coinstate

        if message.items == []:
            self.local_peer.logger.info("%15s ConnectedRemotePeer.waiting_for_inventory=False" % self.host)
            self.waiting_for_inventory = False
            return

        if len(message.items) > GET_BLOCKS_INVENTORY_SIZE:
            raise Exception("Inventory msg too big")

        coinstate = self.local_peer.chain_manager.coinstate

        starting_height = coinstate.get_block_by_hash(
            message.items[0].hash
        ).height if coinstate.has_block_hash(message.items[0].hash) else None

        self.local_peer.logger.info(
            "%15s inventory starting hash corresponds to height=%s" % (
                self.host, str(starting_height) if starting_height else "Unknown"))

        if coinstate.head().height > 1 and starting_height == 1:
            # It is not clear what causes this scenario to happen, but it's in the logs.
            self.local_peer.logger.info("%15s iventory at genesis block discarded" % self.host)
            self.waiting_for_inventory = False
            return

        for msg_state in self.inventory_messages:
            for item in msg_state.message.items:
                if item.hash == message.items[-1].hash:
                    self.local_peer.logger.info("%15s ... already have this inventory" % self.host)
                    return

        self.inventory_messages.append(InventoryMessageState(header, message))
        self.check_inventory_messages()

        # speed optimization: go ahead and ask for more inventory now, there is no reason to wait
        get_blocks_message = GetBlocksMessage([msg.hash for msg in message.items[-1:-10:-1]])

        if self.local_peer.logger.isEnabledFor(logging.INFO):
            self.local_peer.logger.info(
                "%15s requesting more blocks, start=[%s], stop=%s" % (
                    self.host,
                    [human(h) for h in get_blocks_message.potential_start_hashes],
                    human(get_blocks_message.stop_hash)))

        self.send_message(get_blocks_message, prev_header=header)

    def check_inventory_messages(self) -> None:
        coinstate = self.local_peer.chain_manager.coinstate
        requested = 0

        for msg_state in self.inventory_messages:
            if not msg_state.actually_used:
                msg_state.actually_used = True
                for item in msg_state.message.items:

                    if not item.block_requested and not coinstate.has_block_hash(item.hash):
                        item.block_requested = True
                        self.send_message(GetDataMessage(DATA_BLOCK, item.hash), prev_header=msg_state.header)
                        requested += 1

        self.local_peer.logger.info("%15s ConnectedRemotePeer.check_inventory_messages() requested=%d" %
                                    (self.host, requested))

    def remove_from_inventory(self, hash: bytes) -> bool:
        for i, msg_state in enumerate(self.inventory_messages):
            for j, item in enumerate(msg_state.message.items):
                if item.hash == hash:
                    del msg_state.message.items[j]
                    break
            if len(msg_state.message.items) == 0:
                del self.inventory_messages[i]
                return True
        return False

    def handle_get_data_message_received(
        self, header: MessageHeader, get_data_message: GetDataMessage
    ) -> None:

        if get_data_message.data_type != DATA_BLOCK:
            raise NotImplementedError("We can only deal w/ DATA_BLOCK GetDataMessage objects for now")

        self.local_peer.logger.info(
            "%15s ConnectedRemotePeer.handle_get_data_message_received(hash=%s)" % (
                self.host, human(get_data_message.hash)))

        coinstate = self.local_peer.chain_manager.coinstate

        if not coinstate.has_block_hash(get_data_message.hash):
            # we simply silently ignore GetDataMessage for hashes we don't have... future work: inc banscore, or ...
            self.local_peer.logger.info("%15s ConnectedRemotePeer.handle_data_message_received for unknown hash %s" % (
                self.host, human(get_data_message.hash)))
            return

        block = coinstate.get_block_by_hash(get_data_message.hash)
        self.local_peer.logger.info("%15s ... height = %d" % (self.host, block.height))

        data_message = DataMessage(DATA_BLOCK, block)

        self.send_message(data_message, prev_header=header)
        self.height_sent = block.height

    def handle_data_message_received(self, header: MessageHeader, message: DataMessage) -> None:
        self.local_peer.logger.debug(
            "%15s ConnectedRemotePeer.handle_data_message_received(type=%s format=%s)" % (
             self.host, str(DATATYPES[message.data_type]), header.format()))

        if message.data_type == DATA_BLOCK:
            return self.handle_block_received(header, message)

        if message.data_type == DATA_TRANSACTION:
            return self.handle_transaction_received(header, message)

        raise NotImplementedError("Unknown DataMessage objects for now")

    def handle_block_received(
        self, header: MessageHeader, message: DataMessage
    ) -> None:
        block: Block = message.data  # type: ignore

        self.local_peer.logger.debug(
            "%15s ConnectedRemotePeer.handle_block_received(type=%s format=%s height=%d)" % (
             self.host, str(DATATYPES[message.data_type]), header.format(), block.height))

        if header.in_response_to != 0:
            # delay new inventory requests for a peer that's still sending inventory blocks
            self.last_inventory_response_at = int(time())

        flush = self.remove_from_inventory(block.hash())

        # this validation is not quite as effective if done later
        if block.timestamp > int(time()) + 2 * 60:
            self.local_peer.logger.info("%15s ... block is from the future, rejecting: %s" % (
                self.host, str(block)))
            return

        self.block_receive_buffer.append(block)

        if flush or header.in_response_to == 0:

            coinstate = self.local_peer.chain_manager.coinstate.add_block_batch(self.block_receive_buffer)
            self.block_receive_buffer = []
            self.local_peer.chain_manager.set_coinstate(coinstate)

        self.height_received = block.height

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
            if con_peer.direction == OUTGOING and con_peer.ban_score < MAX_CONNECTION_ATTEMPTS:
                peers.append(Peer(int(time()), IPv6Address("::FFFF:%s" % con_peer.host), con_peer.port))

        for discon_peer in self.local_peer.network_manager.disconnected_peers.values():
            if discon_peer.direction == OUTGOING and discon_peer.ban_score < MAX_CONNECTION_ATTEMPTS:
                peers.append(Peer(0, IPv6Address("::FFFF:%s" % discon_peer.host),
                             discon_peer.port))  # TODO 'last seen' time.

        # TODO filter out local network addresses (also on the receiving end)
        peers = peers[:1000]  # send 1000 peers max.

        self.send_message(PeersMessage(peers), prev_header=header)

    def handle_peers_message_received(
        self, header: MessageHeader, message: PeersMessage
    ) -> None:
        # Peers that have been communicated to you like this are not allowed to overwrite the ban_score, to help
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

            if key in nm.disconnected_peers:
                if nm.disconnected_peers[key].ban_score > 0:
                    self.local_peer.logger.info("%15s (ban_score=%d) is broadcasting peer %s (ban_score=%d)" %
                                                (self.host, self.ban_score, nm.disconnected_peers[key].host,
                                                 nm.disconnected_peers[key].ban_score))

            elif key not in nm.connected_peers:
                nm.disconnected_peers[key] = DisconnectedRemotePeer(host, announced_peer.port, OUTGOING, None,
                                                                    ban_score=0)

            nm._sanity_check()
