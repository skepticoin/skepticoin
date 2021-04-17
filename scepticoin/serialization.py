from io import BytesIO
import struct


class DeserializationError(Exception):
    pass


class SerializationError(Exception):
    pass


class SerializationTruncationError(SerializationError):
    pass


class Serializable:
    def serialize(self):
        f = BytesIO()
        self.stream_serialize(f)
        return f.getvalue()

    @classmethod
    def deserialize(cls, bytes_):
        f = BytesIO(bytes_)
        f.seek(0)
        return cls.stream_deserialize(f)


def safe_read(f, n):
    r = f.read(n)

    if len(r) < n:
        raise SerializationTruncationError('Requested %i bytes but got %i' % (n, len(r)))

    return r


def stream_serialize_list(f, l):
    stream_serialize_vlq(f, len(l))
    for elem in l:
        elem.stream_serialize(f)


def stream_deserialize_list(f, clz):
    result = []
    length = stream_deserialize_vlq(f)
    for i in range(length):
        result.append(clz.stream_deserialize(f))
    return result


def serialize_list(l):
    f = BytesIO()
    stream_serialize_list(f, l)
    return f.getvalue()


def deserialize_list(cls, bytes_):
    f = BytesIO(bytes_)
    f.seek(0)
    return cls.stream_deserialize(f)


def stream_serialize_vlq(f, i):
    r"""From wikipedia: https://en.wikipedia.org/wiki/Variable-length_quantity

    The encoding assumes an octet (an eight-bit byte) where the most significant bit (MSB), also commonly known as the
    sign bit, is reserved to indicate whether another VLQ octet follows.

    If the MSB is 0, then this is the last VLQ octet of the integer, if it is 1, then another VLQ octet follows. The
    other 7 bits are treated as a 7-bit number. The VLQ octets are arranged most significant first in a stream."""
    needed_bytes = (i.bit_length() // 7) + 1

    mod = None
    for j in reversed(range(needed_bytes)):
        div = pow(128, j)
        f.write(struct.pack(b"B", (i % mod if mod else i) // div + (128 if j > 0 else 0)))
        mod = div


def stream_deserialize_vlq(f):
    """ """
    result = 0

    while True:
        (b,) = struct.unpack(b"B", safe_read(f, 1))

        result += (b % 128)

        if b < 128:
            return result

        result *= 128
