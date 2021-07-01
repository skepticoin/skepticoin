import cProfile
import pickle


# Profiling results: before optimizations, Block Height 73000
#   first run: 308 seconds
#   - 86% of time is spent in io.open()
#   - 10% in add_block_no_validation()
#   - <5% in serialize()
#   second run (disk cache in effect?): 42 seconds
#   - 65% of time is spent in add_block_no_validation()
#   - 25% of time is in serialize()
# After optimization:
#   first run: 14 seconds
#   - this is fast enough for now, didn't analyse details.
#   - later increased to 17 seconds after removing some of the hash() caching

from skepticoin.scripts.utils import (
    check_chain_dir,
    read_chain_from_disk
)
from skepticoin.coinstate import CoinState


def test_read_chain_from_disk():

    check_chain_dir()

    with cProfile.Profile() as pr:
        coinstate = pr.runcall(read_chain_from_disk)
        pr.print_stats()

    with open('test.tmp', 'wb') as file:
        coinstate.dump(lambda data: pickle.dump(data, file))


def test_faster_read():

    with open('test.tmp', 'rb') as file:
        with cProfile.Profile() as pr:
            pr.runcall(lambda: CoinState.load(lambda: pickle.load(file)))
            pr.print_stats()
