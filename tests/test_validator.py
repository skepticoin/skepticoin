
from skepticoin.validator import Validator
from skepticoin.networking.threading import NetworkingThread
from tests.networking.test_integration import FakeDiskInterface
from tests.test_db import read_test_chain_from_disk


def test_validator():
    coinstate = read_test_chain_from_disk(5, "-validator")

    thread = NetworkingThread(coinstate, 12500, FakeDiskInterface())
    thread.start()

    coinstate = thread.local_peer.chain_manager.coinstate

    validator = Validator()

    for _ in range(0, 5):
        validator.step(thread.local_peer.chain_manager)

    validator.join()

    assert thread.local_peer.chain_manager.coinstate.head().height == 5

    coinstate.blockstore.update("update chain set pow_chain_sample = x'deadbeef' where height = 3")
    coinstate.blockstore.update("delete from validation_tracker")
    validator = Validator()

    print("The following part of the test is expected to log validation errors:")
    for _ in range(0, 5):
        validator.step(thread.local_peer.chain_manager)

    validator.join()

    assert thread.local_peer.chain_manager.coinstate.head().height == 2
    assert len(thread.local_peer.chain_manager.coinstate.heads) == 1
