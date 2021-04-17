from io import BytesIO
from scepticoin.serialization import stream_deserialize_vlq, stream_serialize_vlq


def test_vlq():
    test_cases = [0, 1, 42, 0x7f, 0x80, 0x2000, 0x3fff, 0x4000, 1234567890]
    for i in test_cases:
        f = BytesIO()
        stream_serialize_vlq(f, i)

        f.seek(0)
        assert stream_deserialize_vlq(f) == i
