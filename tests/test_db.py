from skepticoin.chain_db import BlockChainDatabase
from skepticoin.coinstate import CoinState
from skepticoin.humans import human
import os


def test_db():
    coinstate = CoinState.zero()

    if os.path.exists('test.db'):
        os.remove('test.db')

    db = BlockChainDatabase(path='test.db')
    db.write_chain_to_disk(coinstate)

    cur = db.connection.cursor()
    for row in cur.execute("select count(*) from chain"):
        assert row[0] == 1

    readstate = db.read_chain_from_disk()

    block1 = list(readstate.block_by_hash.values())[0]
    block2 = list(coinstate.block_by_hash.values())[0]

    assert block1.hash() == block2.hash()
    assert block1.serialize() == block2.serialize()
    assert block1.transactions == block2.transactions
    assert human(block1.hash()) == '00c4ff1d0788c7058f3d8388d77b2feda0921fa141078fb895871634e0c36780'

    db.close()
