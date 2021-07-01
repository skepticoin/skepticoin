"Profile the performance of downloading fresh chain from peers"

from skepticoin.networking.threading import NetworkingThread

from skepticoin.scripts.utils import (
    configure_logging_from_args,
    DefaultArgumentParser,
    check_chain_dir,
    read_chain_from_disk,
)
import cProfile
from datetime import datetime
from time import time


def test_main():
    parser = DefaultArgumentParser()
    args = parser.parse_args(args=[])
    configure_logging_from_args(args)

    # Initially were using an empty chain for this test.
    # And then we found that the performance of newer blocks is different!
    # coinstate = CoinState.zero()
    check_chain_dir()
    coinstate = read_chain_from_disk()

    # we need to run in the current thread to profile it
    nt = NetworkingThread(coinstate, port=None)

    def runner():
        started = datetime.now()
        nt.local_peer.running = True
        print("start height = %d" % nt.local_peer.chain_manager.coinstate.head().height)
        while (datetime.now() - started).seconds <= 100:
            current_time = int(time())
            nt.local_peer.step_managers(current_time)
            nt.local_peer.handle_selector_events()
        print("final height = %d" % nt.local_peer.chain_manager.coinstate.head().height)

    with cProfile.Profile() as pr:
        pr.runcall(runner)
        pr.print_stats()
