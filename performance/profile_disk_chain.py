import cProfile
from datetime import datetime

from skepticoin.scripts.utils import read_chain_from_disk

# Run with: python -m pytest performance/profile_disk_chain.py -s

# Sample output (YMMV):
#
# performance/profile_disk_chain.py Reading chain.db
#          28908648 function calls (28908646 primitive calls) in 90.558 seconds

#    Ordered by: cumulative time

#    ncalls  tottime  percall  cumtime  percall filename:lineno(function)
#         1    0.000    0.000   90.558   90.558 cProfile.py:106(runcall)
#         1    1.298    1.298   90.558   90.558 utils.py:44(read_chain_from_disk)
#    317234   14.483    0.000   59.835    0.000 coinstate.py:88(add_block_no_validation)
#   1268932   29.742    0.000   29.742    0.000 {method 'set' of 'immutables._map.Map' objects}
#    317234    4.632    0.000   29.424    0.000 blockstore.py:182(read_blocks_from_disk)
#    671729    1.438    0.000   12.018    0.000 serialization.py:26(deserialize)
#         1    2.234    2.234   10.947   10.947 blockstore.py:167(load_inputs)
#         1    1.309    1.309    6.258    6.258 blockstore.py:177(load_outputs)
#    353747    0.612    0.000    6.228    0.000 signing.py:80(stream_deserialize)
#    317234    0.581    0.000    6.009    0.000 balances.py:33(uto_apply_block)
#    317646    3.303    0.000    5.429    0.000 balances.py:12(uto_apply_transaction)
#   1977945    2.945    0.000    4.768    0.000 serialization.py:40(safe_read)
#    317234    1.239    0.000    4.546    0.000 signing.py:146(stream_deserialize)
#    317233    1.888    0.000    4.417    0.000 blockstore.py:219(<listcomp>)
#    317983    0.540    0.000    4.010    0.000 signing.py:28(stream_deserialize)
#    634880    3.714    0.000    3.714    0.000 {method 'mutate' of 'immutables._map.Map' objects}
#   2220633    2.529    0.000    3.627    0.000 datatypes.py:328(__getattr__)
#    317983    0.522    0.000    2.689    0.000 signing.py:56(stream_deserialize)
#    317235    1.227    0.000    2.087    0.000 coinstate.py:16(__init__)
#    635290    1.140    0.000    1.517    0.000 {built-in method builtins.sorted}
#   3321406    1.514    0.000    1.514    0.000 {built-in method builtins.len}
#         1    0.000    0.000    1.448    1.448 blockstore.py:160(load_transaction_builders)
#         1    0.771    0.771    1.442    1.442 blockstore.py:161(<dictcomp>)
#    671730    1.102    0.000    1.437    0.000 datatypes.py:23(__init__)
#    317983    1.252    0.000    1.393    0.000 signing.py:41(__init__)
#   2220633    1.098    0.000    1.098    0.000 {built-in method builtins.getattr}


def test_read_chain_from_disk():

    with cProfile.Profile() as pr:
        started = datetime.now()
        coinstate = pr.runcall(read_chain_from_disk)
        pr.print_stats(sort='cumulative')
        n = len(coinstate.block_by_hash.keys())
        ended = datetime.now()
        bpm = n / ((ended - started).seconds / 60)
        print(f"read {n} blocks in {ended - started}: {bpm} blocks per minute")
