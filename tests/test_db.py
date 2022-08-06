from skepticoin.blockstore import BlockStore
from skepticoin.coinstate import CoinState
from skepticoin.humans import human
import os

from skepticoin.scripts.utils import open_or_init_wallet


def test_db():
    coinstate = CoinState.zero()

    if os.path.exists('test.db'):
        os.remove('test.db')

    db = BlockStore(path='test.db')
    for block in coinstate.block_by_hash.values():
        db.add_block_to_buffer(block)

    db.flush_blocks_to_disk()

    cur = db.connection.cursor()
    for row in cur.execute("select count(*) from chain"):
        assert row[0] == 1

    readstate = CoinState.zero()
    for block in db.read_blocks_from_disk():
        readstate.add_block_no_validation(block)

    block1 = list(readstate.block_by_hash.values())[0]
    block2 = list(coinstate.block_by_hash.values())[0]

    assert block1.hash() == block2.hash()
    assert block1.serialize() == block2.serialize()
    assert block1.transactions == block2.transactions
    assert human(block1.hash()) == '00c4ff1d0788c7058f3d8388d77b2feda0921fa141078fb895871634e0c36780'

    wallet = open_or_init_wallet()
    assert wallet.get_balance(coinstate) == 0

    db.close()
