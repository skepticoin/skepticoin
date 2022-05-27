from skepticoin.coinstate import CoinState
from skepticoin.datatypes import Block
from skepticoin.scripts.utils import read_chain_from_disk
from skepticoin.networking.disk_interface import DiskInterface
from test_consensus import get_example_genesis_block
import io
import shutil
import plyvel as leveldb


def test_block_serialization():
    block = get_example_genesis_block()
    with io.BytesIO() as buffer:
        block.stream_serialize(buffer)
        buffer.seek(0)
        bytes = buffer.read()
        assert len(bytes) != 0
        readblock = Block.stream_deserialize(io.BytesIO(bytes))
        assert(readblock.header.hash() == block.header.hash())


def test_db():
    coinstate = CoinState.zero()
    coinstate = coinstate.add_block_no_validation(get_example_genesis_block())

    shutil.rmtree('test.db', ignore_errors=True)
    DiskInterface().write_chain_to_disk(coinstate, path='test.db')

    db = leveldb.DB('test.db')
    with db.iterator() as it:
        for hash, block in it:
            assert len(hash) != 0
            assert len(block) != 0
    db.close()

    readstate = read_chain_from_disk(path='test.db')
    assert(list(readstate.block_by_hash.keys())[0] == list(coinstate.block_by_hash.keys())[0])
    shutil.rmtree('test.db')
