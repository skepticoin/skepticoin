from skepticoin.scripts.utils import read_chain_from_disk
from skepticoin.consensus import validate_block_in_coinstate


def test_large_transaction():

    coinstate = read_chain_from_disk()

    if coinstate.head_block.height < 246602:
        return

    block = coinstate.block_by_height_at_head(246602)
    validate_block_in_coinstate(block, coinstate)
