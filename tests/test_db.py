from pathlib import Path
from skepticoin.balances import get_balance
from skepticoin.blockstore import BlockStore
from skepticoin.coinstate import CoinState
from skepticoin.datatypes import Block
from skepticoin.humans import human
import os

from skepticoin.scripts.utils import open_or_init_wallet

CHAIN_TESTDATA_PATH = Path(__file__).parent.joinpath("testdata/chain")


def read_test_chain_from_disk(max_height, suffix: str = "-default"):
    coinstate = CoinState(setup_test_db(suffix))

    for file_path in sorted(CHAIN_TESTDATA_PATH.iterdir()):
        height = int(file_path.name.split("-")[0])
        if height > max_height:
            return coinstate

        block = Block.stream_deserialize(open(file_path, 'rb'))
        coinstate = coinstate.add_block_batch([block])

    return coinstate


def test_chain_index():
    coinstate = read_test_chain_from_disk(5)
    assert coinstate.get_block_id_path(coinstate.current_chain_hash) == [1, 2, 3, 4, 5, 6]


def setup_test_db(suffix: str = ""):
    DATABASE_FILE_PATH = str(Path(__file__).parent.joinpath(f"testdata/test-{suffix}.db"))

    if os.path.exists(DATABASE_FILE_PATH):
        os.remove(DATABASE_FILE_PATH)

    return BlockStore(path=DATABASE_FILE_PATH)


def test_db_genesis():
    blockstore = setup_test_db("genesis")
    coinstate = CoinState(blockstore)

    rows = blockstore.sql("select block_id from chain")
    assert len(rows) == 1
    assert rows[0][0] == 1

    block1 = coinstate.block_by_height_at_head(0)

    assert human(block1.hash()) == '00c4ff1d0788c7058f3d8388d77b2feda0921fa141078fb895871634e0c36780'

    wallet = open_or_init_wallet()
    assert get_balance(wallet, coinstate) == 0
