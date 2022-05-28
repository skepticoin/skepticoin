import cProfile
from skepticoin.chain_db import DefaultDatabase

# New profiling results using sqlite3
# baseline:
# - total time: 177 seconds, height=275000
# - slowest methods:
#       1375006   38.830    0.000   38.830    0.000 {method 'set' of 'immutables._map.Map' objects}
#       2553496    5.129    0.000   53.375    0.000 serialization.py:21(serialize) -- related to signing.py


def test_read_chain_from_disk():

    with cProfile.Profile() as pr:
        pr.runcall(lambda: DefaultDatabase.instance.read_chain_from_disk())
        pr.print_stats()
