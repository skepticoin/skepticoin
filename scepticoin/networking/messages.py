import struct
from ipaddress import IPv6Address

from ..serialization import (
    DeserializationError,
    safe_read,
    Serializable,
    stream_deserialize_list,
    stream_deserialize_vlq,
    stream_serialize_list,
    stream_serialize_vlq,
)
from ..datatypes import Block, BlockHeader, Transaction


MSG_HELLO = b'\x00\x00'
MSG_GET_BLOCKS = b'\x00\x01'
MSG_INVENTORY = b'\x00\x02'
MSG_GET_DATA = b'\x00\x03'
MSG_DATA = b'\x00\x04'
MSG_GET_PEERS = b'\x00\x05'
MSG_PEERS = b'\x00\x06'

DATA_BLOCK = b'\x00\x00'
DATA_HEADER = b'\x00\x01'
DATA_TRANSACTION = b'\x00\x02'


DATATYPES = {
    DATA_BLOCK: Block,
    DATA_HEADER: BlockHeader,
    DATA_TRANSACTION: Transaction,
}


class MessageHeader(Serializable):
    def __init__(self, timestamp, id, in_response_to, context):
        self.version = 0
        self.timestamp = timestamp
        self.id = id
        self.in_response_to = in_response_to
        self.context = context

    @classmethod
    def stream_deserialize(cls, f):
        # version is ignored... we parse everything as version 0, since that's the only thing we ourselves speak.
        # once other versions get introduced we should start paying attention to what's in here, and parse as much as we
        # know about
        (version,) = struct.unpack(b"B", safe_read(f, 1))

        (timestamp,) = struct.unpack(b">I", safe_read(f, 4))
        (id,) = struct.unpack(b">I", safe_read(f, 4))
        (in_response_to,) = struct.unpack(b">I", safe_read(f, 4))
        (context,) = struct.unpack(b">Q", safe_read(f, 8))

        safe_read(f, 32)  # reserved space for later versions

        return cls(timestamp, id, in_response_to, context)

    def stream_serialize(self, f):
        f.write(struct.pack(b"B", self.version))

        f.write(struct.pack(b">I", self.timestamp))
        f.write(struct.pack(b">I", self.id))
        f.write(struct.pack(b">I", self.in_response_to))
        f.write(struct.pack(b">Q", self.context))

        f.write(b'\x00' * 32)  # reserved space for later versions

    def format(self):
        return "t%010d-i%010d-r%010d-c%020d" % (self.timestamp, self.id, self.in_response_to, self.context)


class Message(Serializable):

    @classmethod
    def stream_deserialize(cls, f):
        type_indicator = safe_read(f, 2)

        if type_indicator == MSG_HELLO:
            return HelloMessage.stream_deserialize(f)

        if type_indicator == MSG_GET_BLOCKS:
            return GetBlocksMessage.stream_deserialize(f)

        if type_indicator == MSG_INVENTORY:
            return InventoryMessage.stream_deserialize(f)

        if type_indicator == MSG_GET_DATA:
            return GetDataMessage.stream_deserialize(f)

        if type_indicator == MSG_DATA:
            return DataMessage.stream_deserialize(f)

        if type_indicator == MSG_GET_PEERS:
            return GetPeersMessage.stream_deserialize(f)

        if type_indicator == MSG_PEERS:
            return PeersMessage.stream_deserialize(f)

        raise DeserializationError("Non-supported message type")


class SupportedVersion(Serializable):

    def __init__(self, version):
        self.version = version

    @classmethod
    def stream_deserialize(cls, f):
        (version,) = struct.unpack(b"B", safe_read(f, 1))
        return cls(version)

    def stream_serialize(self, f):
        f.write(struct.pack(b"B", self.version))


class HelloMessage(Message):

    def __init__(self, supported_versions, your_ip_address, your_port, my_ip_address, my_port, nonce, user_agent):
        self.version = 0
        self.supported_versions = supported_versions

        # capabilities? (bitcoin calls this "services")... for now we imply that everyone is a full node.

        self.your_ip_address = your_ip_address
        self.your_port = your_port

        self.my_ip_address = my_ip_address
        self.my_port = my_port

        self.nonce = nonce

        self.user_agent = user_agent

    @classmethod
    def stream_deserialize(cls, f):
        # type_indicator has been read already by the superclass at this point.

        # version is ignored... we parse everything as version 0, since that's the only thing we ourselves speak.
        # once other versions get introduced we should start paying attention to what's in here, and parse as much as we
        # know about.
        (version,) = struct.unpack(b"B", safe_read(f, 1))

        your_ip_address = IPv6Address(safe_read(f, 16))
        (your_port,) = struct.unpack(b">H", safe_read(f, 2))

        my_ip_address = IPv6Address(safe_read(f, 16))
        (my_port,) = struct.unpack(b">H", safe_read(f, 2))

        (nonce,) = struct.unpack(b">I", safe_read(f, 4))

        (ua_length,) = struct.unpack(b"B", safe_read(f, 1))
        user_agent = safe_read(f, ua_length)

        supported_versions = stream_deserialize_list(f, SupportedVersion)

        safe_read(f, 256)  # reserved space for later versions

        return cls(supported_versions, your_ip_address, your_port, my_ip_address, my_port, nonce, user_agent)

    def stream_serialize(self, f):
        f.write(MSG_HELLO)
        f.write(struct.pack(b"B", self.version))

        f.write(self.your_ip_address.packed)
        f.write(struct.pack(b">H", self.your_port))

        f.write(self.my_ip_address.packed)
        f.write(struct.pack(b">H", self.my_port))

        f.write(struct.pack(b">I", self.nonce))

        f.write(struct.pack(b"B", len(self.user_agent)))
        f.write(self.user_agent)

        stream_serialize_list(f, self.supported_versions)

        f.write(b'\x00' * 256)  # reserved space for later versions


class GetBlocksMessage(Message):

    def __init__(self, potential_start_hashes, stop_hash=b'\x00' * 32):
        self.version = 0

        self.potential_start_hashes = potential_start_hashes
        self.stop_hash = stop_hash

    @classmethod
    def stream_deserialize(cls, f):
        # type_indicator has been read already by the superclass at this point.
        if safe_read(f, 1) != b'\x00':
            raise ValueError("Current version supports only version 0 GetBlocksMessage")

        potential_start_hashes = []
        length = stream_deserialize_vlq(f)
        for i in range(length):
            potential_start_hashes.append(safe_read(f, 32))

        stop_hash = safe_read(f, 32)
        return cls(potential_start_hashes, stop_hash)

    def stream_serialize(self, f):
        f.write(MSG_GET_BLOCKS)
        f.write(struct.pack(b"B", self.version))

        stream_serialize_vlq(f, len(self.potential_start_hashes))
        for h in self.potential_start_hashes:
            f.write(h)

        f.write(self.stop_hash)


class InventoryItem(Serializable):

    def __init__(self, data_type, hash):
        self.data_type = data_type
        self.hash = hash

    @classmethod
    def stream_deserialize(cls, f):
        data_type = safe_read(f, 2)
        hash = safe_read(f, 32)
        return cls(data_type, hash)

    def stream_serialize(self, f):
        f.write(self.data_type)
        f.write(self.hash)


class InventoryMessage(Message):

    def __init__(self, items):
        self.version = 0
        self.items = items

    @classmethod
    def stream_deserialize(cls, f):
        # type_indicator has been read already by the superclass at this point.
        if safe_read(f, 1) != b'\x00':
            raise ValueError("Current version supports only version 0 InventoryMessage")

        items = stream_deserialize_list(f, InventoryItem)
        return cls(items)

    def stream_serialize(self, f):
        f.write(MSG_INVENTORY)
        f.write(struct.pack(b"B", self.version))

        stream_serialize_list(f, self.items)


class GetDataMessage(Message):

    def __init__(self, data_type, hash):
        self.version = 0
        self.data_type = data_type
        self.hash = hash

    @classmethod
    def stream_deserialize(cls, f):
        # type_indicator has been read already by the superclass at this point.
        if safe_read(f, 1) != b'\x00':
            raise ValueError("Current version supports only version 0 GetDataMessage")

        data_type = safe_read(f, 2)
        hash = safe_read(f, 32)

        return cls(data_type, hash)

    def stream_serialize(self, f):
        f.write(MSG_GET_DATA)
        f.write(struct.pack(b"B", self.version))

        f.write(self.data_type)
        f.write(self.hash)


class DataMessage(Message):

    def __init__(self, data_type, data):
        self.version = 0

        self.data_type = data_type
        self.data = data

    @classmethod
    def stream_deserialize(cls, f):
        # type_indicator has been read already by the superclass at this point.
        if safe_read(f, 1) != b'\x00':
            raise ValueError("Current version supports only version 0 DataMessage")

        data_type = safe_read(f, 2)

        clz = DATATYPES[data_type]
        data = clz.stream_deserialize(f)

        return cls(data_type, data)

    def stream_serialize(self, f):
        f.write(MSG_DATA)
        f.write(struct.pack(b"B", self.version))

        f.write(self.data_type)
        self.data.stream_serialize(f)


class GetPeersMessage(Message):

    def __init__(self):
        self.version = 0

    @classmethod
    def stream_deserialize(cls, f):
        # type_indicator has been read already by the superclass at this point.
        if safe_read(f, 1) != b'\x00':
            raise ValueError("Current version supports only version 0 GetPeersMessage")

        return cls()

    def stream_serialize(self, f):
        f.write(MSG_GET_PEERS)
        f.write(struct.pack(b"B", self.version))


class Peer(Serializable):

    def __init__(self, last_seen_at, ip_address, port):
        self.last_seen_at = last_seen_at
        self.ip_address = ip_address
        self.port = port

    @classmethod
    def stream_deserialize(cls, f):
        (last_seen_at,) = struct.unpack(b">I", safe_read(f, 4))
        ip_address = IPv6Address(safe_read(f, 16))
        (port,) = struct.unpack(b">H", safe_read(f, 2))

        return cls(last_seen_at, ip_address, port)

    def stream_serialize(self, f):
        f.write(struct.pack(b">I", self.last_seen_at))
        f.write(self.ip_address.packed)
        f.write(struct.pack(b">H", self.port))


class PeersMessage(Message):

    def __init__(self, peers):
        self.version = 0
        self.peers = peers

    @classmethod
    def stream_deserialize(cls, f):
        # type_indicator has been read already by the superclass at this point.
        if safe_read(f, 1) != b'\x00':
            raise ValueError("Current version supports only version 0 GetPeersMessage")

        peers = stream_deserialize_list(f, Peer)

        return cls(peers)

    def stream_serialize(self, f):
        f.write(MSG_PEERS)
        f.write(struct.pack(b"B", self.version))
        stream_serialize_list(f, self.peers)


__all__ = [
    "MessageHeader",
    "Message",
    "SupportedVersion",
    "HelloMessage",
    "GetBlocksMessage",
    "InventoryItem",
    "InventoryMessage",
    "GetDataMessage",
    "DataMessage",
    "GetPeersMessage",
    "Peer",
    "PeersMessage",
]
