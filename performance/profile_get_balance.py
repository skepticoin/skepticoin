import cProfile
from datetime import datetime
from skepticoin.balances import get_balance
from skepticoin.params import SASHIMI_PER_COIN

from skepticoin.scripts.utils import open_or_init_wallet, read_chain_from_disk

# Test CPU performance:
#
#    python -m pytest performance/profile_get_balance.py -s
#
# Test memory utilization (Linux/WSL only - no Windows):
#
#   pip install memray
#   rm -f memray.out memray-*.html
#   python -m memray run -o memray.out performance/profile_get_balance.py
#   python -m memray tree memray.out
#   python -m memray flamegraph memray.out
#   python -m memray summary memray.out


def steps():
    coinstate = read_chain_from_disk()
    wallet = open_or_init_wallet()
    print(
        get_balance(wallet, coinstate) / SASHIMI_PER_COIN, "SKEPTI at h. %s," % coinstate.head().height,
        datetime.fromtimestamp(coinstate.head().timestamp).isoformat())


def test_get_balance():

    with cProfile.Profile() as pr:
        pr.runcall(steps)
        pr.print_stats(sort='cumulative')


if __name__ == '__main__':
    steps()
