"Profile the performance of downloading fresh chain from peers"

from skepticoin.networking.disk_interface import DiskInterface
from skepticoin.networking.threading import NetworkingThread

from skepticoin.scripts.utils import (
    configure_logging_from_args,
    DefaultArgumentParser,
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
    coinstate = read_chain_from_disk()
    disk_interface = DiskInterface(1000)

    # we need to run in the current thread to profile it
    nt = NetworkingThread(coinstate, 2499, disk_interface, args)

    def runner():
        started = datetime.now()
        nt.local_peer.running = True
        start_height = nt.local_peer.chain_manager.coinstate.head().height
        print("start height = %d" % start_height)
        while (datetime.now() - started).seconds <= 60:
            current_time = int(time())
            nt.local_peer.step_managers(current_time)
            nt.local_peer.handle_selector_events()
        end_height = nt.local_peer.chain_manager.coinstate.head().height
        print("final height = %d" % end_height)
        elapsed = datetime.now() - started
        return (start_height, end_height, elapsed)

    with cProfile.Profile() as pr:
        (start_height, end_height, elapsed) = pr.runcall(runner)
        tps = (end_height-start_height) // (elapsed.seconds/60)
        pr.print_stats(sort='cumulative')
        print(f"start={start_height} end={end_height} elapsed={elapsed} throughput={tps} bpm")
