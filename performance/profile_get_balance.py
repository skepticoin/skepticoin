import cProfile
from datetime import datetime
from skepticoin.params import SASHIMI_PER_COIN

from skepticoin.scripts.utils import open_or_init_wallet, read_chain_from_disk

# Run with: python -m pytest performance/profile_get_balance.py -s


def steps():
    coinstate = read_chain_from_disk()
    wallet = open_or_init_wallet()
    print(
        wallet.get_balance(coinstate) / SASHIMI_PER_COIN, "SKEPTI at h. %s," % coinstate.head().height,
        datetime.fromtimestamp(coinstate.head().timestamp).isoformat())


def test_get_balance():

    with cProfile.Profile() as pr:
        pr.runcall(steps)
        pr.print_stats(sort='cumulative')
