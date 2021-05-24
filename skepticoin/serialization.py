from __future__ import annotations

import struct
from io import BytesIO
from typing import Any, BinaryIO, List, Sequence, Type


class DeserializationError(Exception):
    pass


class SerializationError(Exception):
    pass


class SerializationTruncationError(SerializationError):
    pass


class Serializable:
    def serialize(self) -> bytes:
        f = BytesIO()
        self.stream_serialize(f)
        return f.getvalue()

    @classmethod
    def deserialize(cls, bytes_: bytes) -> Any:
        f = BytesIO(bytes_)
        f.seek(0)
        return cls.stream_deserialize(f)

    def stream_serialize(self, f: BinaryIO) -> None:
        raise NotImplementedError

    @classmethod
    def stream_deserialize(cls, f: BinaryIO) -> Serializable:
        raise NotImplementedError


def safe_read(f: BinaryIO, n: int) -> bytes:
    r: bytes = f.read(n)

    if len(r) < n:
        raise SerializationTruncationError('Requested %i bytes but got %i' % (n, len(r)))

    return r


def stream_serialize_list(f: BinaryIO, lst: Sequence[Serializable]) -> None:
    stream_serialize_vlq(f, len(lst))
    for elem in lst:
        elem.stream_serialize(f)


def stream_deserialize_list(f: BinaryIO, clz: Type) -> List[Any]:
    result: List[Type] = []
    length = stream_deserialize_vlq(f)
    for _ in range(length):
        result.append(clz.stream_deserialize(f))
    return result


def serialize_list(lst: Sequence[Serializable]) -> bytes:
    f = BytesIO()
    stream_serialize_list(f, lst)
    return f.getvalue()


def deserialize_list(cls: Type, bytes_: bytes) -> Any:
    f = BytesIO(bytes_)
    f.seek(0)
    return cls.stream_deserialize(f)


def stream_serialize_vlq(f: BinaryIO, i: int) -> None:
    r"""From wikipedia: https://en.wikipedia.org/wiki/Variable-length_quantity

    The encoding assumes an octet (an eight-bit byte) where the most significant bit (MSB), also commonly known as the
    sign bit, is reserved to indicate whether another VLQ octet follows.

    If the MSB is 0, then this is the last VLQ octet of the integer, if it is 1, then another VLQ octet follows. The
    other 7 bits are treated as a 7-bit number. The VLQ octets are arranged most significant first in a stream."""
    needed_bytes: int = (i.bit_length() // 7) + 1

    mod = 0
    for j in reversed(range(needed_bytes)):
        div = pow(128, j)
        f.write(struct.pack(b"B", (i % mod if mod else i) // div + (128 if j > 0 else 0)))
        mod = div


def stream_deserialize_vlq(f: BinaryIO) -> int:
    """ """
    result = 0

    while True:
        (b,) = struct.unpack(b"B", safe_read(f, 1))

        result += (b % 128)

        if b < 128:
            return result

        result *= 128
