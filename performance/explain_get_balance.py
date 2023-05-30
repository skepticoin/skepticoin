from datetime import datetime
from skepticoin.balances import get_balance
from skepticoin.params import SASHIMI_PER_COIN

from skepticoin.scripts.utils import open_or_init_wallet, read_chain_from_disk


def test_get_balance():
    coinstate = read_chain_from_disk()
    wallet = open_or_init_wallet()

    coinstate.blockstore.sql = coinstate.blockstore.explain

    print(
        get_balance(wallet, coinstate) / SASHIMI_PER_COIN, "SKEPTI at h. %s," % coinstate.head().height,
        datetime.fromtimestamp(coinstate.head().timestamp).isoformat())
