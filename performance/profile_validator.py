
import cProfile
from pstats import Stats

from time import time
from skepticoin.validator import Validator
from skepticoin.networking.threading import NetworkingThread
from skepticoin.scripts.utils import DefaultArgumentParser, read_chain_from_disk
from tests.networking.test_integration import FakeDiskInterface

ARGS = DefaultArgumentParser().parse_args(args=[])


def test_validator():
    coinstate = read_chain_from_disk()

    thread = NetworkingThread(coinstate, 12500, FakeDiskInterface(), ARGS)
    thread.start()

    coinstate = thread.local_peer.chain_manager.coinstate

    validator = Validator()

    start = time()

    print("Starting validation")
    while time() - start < 60:
        validator.step(thread.local_peer.chain_manager, same_thread=True)


if __name__ == '__main__':

    with cProfile.Profile() as pr:
        pr.runcall(test_validator)
        pr.disable()
        stats = Stats(pr)
        stats.sort_stats('cumulative').print_stats(30)
