from datetime import datetime

from ..params import SASHIMI_PER_COIN
from .utils import (
    DefaultArgumentParser,
    configure_logging_from_args,
    create_chain_dir,
    open_or_init_wallet,
    read_chain_from_disk,
)


def main() -> None:
    parser = DefaultArgumentParser()
    args = parser.parse_args()
    configure_logging_from_args(args)

    create_chain_dir()
    coinstate = read_chain_from_disk()
    wallet = open_or_init_wallet()
    print(
        wallet.get_balance(coinstate) / SASHIMI_PER_COIN,
        "SKEPTI at h. %s," % coinstate.head().height,
        datetime.fromtimestamp(coinstate.head().timestamp).isoformat(),
    )
