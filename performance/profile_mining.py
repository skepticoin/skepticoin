import cProfile
import sys

from skepticoin.mining import MinerWatcher


def runner() -> None:
    sys.argv = ['skepticoin-mine', '-n', '4']
    miner_watcher = MinerWatcher()
    miner_watcher()


with cProfile.Profile() as pr:
    pr.runcall(runner)
    pr.print_stats(sort='cumulative')

# Run with pytest -s performance\profile_mining.py
#
# Results from recent run:
# The next best target for optimization is select_n_k_length_slices_from_chain().
# It is the cause of all the calls to fetch_block().
#
#          166685930 function calls (158539439 primitive calls) in 3776.925 seconds

#    Ordered by: cumulative time

#    ncalls  tottime  percall  cumtime  percall filename:lineno(function)
#         1    0.001    0.001 3776.925 3776.925 cProfile.py:106(runcall)
#         1    0.000    0.000 3776.923 3776.923 profile_mining.py:7(runner)
#         1    0.396    0.396 3776.913 3776.913 mining.py:104(__call__)
#     73296    0.538    0.000 2895.636    0.040 queues.py:92(get)
#     73296    0.454    0.000 2894.270    0.039 connection.py:208(recv_bytes)
#     73296    0.646    0.000 2893.734    0.039 connection.py:294(_recv_bytes)
#     36649 2892.200    0.079 2892.200    0.079 {built-in method _winapi.WaitForMultipleObjects}
#     73295    0.381    0.000  875.326    0.012 mining.py:197(handle_received_message)
#     36647    0.385    0.000  871.240    0.024 mining.py:238(handle_scrypt_output_message)
#    331432   15.585    0.000  685.525    0.002 blockstore.py:185(fetch_block)
#     36676    0.246    0.000  628.893    0.017 consensus.py:161(construct_pow_evidence_after_scrypt)
#     36676    1.101    0.000  627.716    0.017 pow.py:57(select_n_k_length_slices_from_chain)
#    293408    0.896    0.000  624.531    0.002 pow.py:44(select_slice_from_chain)
#    293408    0.351    0.000  610.388    0.002 consensus.py:175(get_block_by_height)
#    293408    0.277    0.000  610.037    0.002 coinstate.py:104(by_height_at_hash)
#    293408    1.053    0.000  609.760    0.002 coinstate.py:101(by_height_at_head)
#    998186  478.686    0.000  478.686    0.000 {method 'execute' of 'sqlite3.Cursor' objects}
#    335260    1.105    0.000  199.212    0.001 blockstore.py:99(__enter__)
#    335260  140.436    0.000  140.436    0.000 {built-in method _sqlite3.connect}
#     36647    0.211    0.000  121.805    0.003 mining.py:224(increment_hash_counter)
#      3673    0.167    0.000  121.550    0.033 mining.py:164(print_stats_line)
#      3675    0.609    0.000  120.121    0.033 coinstate.py:117(forks)
#        30    0.005    0.000   94.610    3.154 wallet.py:97(get_balance)
#        30    0.003    0.000   94.604    3.153 wallet.py:102(get_public_key_balances)
#      3798    0.029    0.000   81.557    0.021 blockstore.py:114(sql)
#      3675    0.123    0.000   76.489    0.021 coinstate.py:120(<listcomp>)
#    371918   57.446    0.000   57.446    0.000 {method 'acquire' of '_thread.lock' objects}
#        30   39.412    1.314   39.422    1.314 wallet.py:128(<listcomp>)
#    335260    0.950    0.000   35.906    0.000 blockstore.py:105(__exit__)
#    335260   34.760    0.000   34.760    0.000 {method 'close' of 'sqlite3.Connection' objects}
# 6933387/696808   17.732    0.000   31.679    0.000 coinstate.py:123(_find_lca)
#        29    0.001    0.000   23.198    0.800 coinstate.py:111(add_block)
#        29    0.168    0.006   22.158    0.764 consensus.py:515(validate_block_in_coinstate)
#        30    2.811    0.094   19.137    0.638 coinstate.py:193(get_chain)
#        29    0.505    0.017   19.079    0.658 consensus.py:428(validate_coinbase_transaction_in_coinstate)
#      3972   16.405    0.004   16.405    0.004 {method 'fetchall' of 'sqlite3.Cursor' objects}
#  34700321   10.744    0.000   13.960    0.000 datatypes.py:326(__getattr__)
#    671690    0.657    0.000   13.163    0.000 serialization.py:21(serialize)
#    293524    0.392    0.000   11.197    0.000 datatypes.py:359(stream_serialize)
# 1064700/403612    1.215    0.000    7.086    0.000 serialization.py:49(stream_serialize_list)
#    766728    1.195    0.000    6.664    0.000 serialization.py:26(deserialize)
#    335260    0.568    0.000    6.157    0.000 blockstore.py:93(locked_cursor)
#    367250    0.521    0.000    5.932    0.000 datatypes.py:163(stream_serialize)
#    335288    4.613    0.000    5.423    0.000 {built-in method builtins.__build_class__}
#    331942    0.719    0.000    5.306    0.000 datatypes.py:307(stream_serialize)
#        30    0.008    0.000    5.070    0.169 wallet.py:236(save_wallet)
#        30    0.015    0.000    4.983    0.166 wallet.py:79(dump)
#   1396671    3.234    0.000    4.572    0.000 serialization.py:75(stream_serialize_vlq)
#        30    0.470    0.016    4.067    0.136 __init__.py:120(dump)
#    331971    0.723    0.000    3.697    0.000 datatypes.py:268(stream_serialize)
#     36648    0.628    0.000    3.647    0.000 mining.py:211(handle_request_scrypt_input_message)
#    434083    0.559    0.000    3.491    0.000 signing.py:80(stream_deserialize)
#    331432    3.460    0.000    3.460    0.000 {method 'fetchone' of 'sqlite3.Cursor' objects}
#  34700412    3.216    0.000    3.216    0.000 {built-in method builtins.getattr}
#    331432    1.369    0.000    3.144    0.000 blockstore.py:242(<listcomp>)
#        29    0.000    0.000    2.821    0.097 consensus.py:146(construct_pow_evidence)
#    331856    0.600    0.000    2.474    0.000 hash.py:5(sha256d)
#        29    0.000    0.000    2.359    0.081 consensus.py:156(construct_summary_hash)
#        29    0.000    0.000    2.359    0.081 hash.py:9(scrypt)
#        29    2.357    0.081    2.359    0.081 scrypt.py:200(hash)
#    331428    0.889    0.000    2.289    0.000 signing.py:146(stream_deserialize)
#   1537005    0.976    0.000    2.226    0.000 {method 'write' of '_io.TextIOWrapper' objects}
#    469561    0.502    0.000    2.084    0.000 datatypes.py:87(stream_serialize)
#         1    0.000    0.000    2.046    2.046 utils.py:38(read_chain_from_disk)
#         1    0.017    0.017    2.044    2.044 coinstate.py:16(__init__)
#   2196312    1.205    0.000    1.799    0.000 serialization.py:40(safe_read)
#     36648    0.120    0.000    1.781    0.000 consensus.py:246(construct_block_pow_evidence_input)
#    332645    0.425    0.000    1.747    0.000 signing.py:28(stream_deserialize)
#   9804737    1.528    0.000    1.528    0.000 {method 'write' of '_io.BytesIO' objects}
#   4990040    1.463    0.000    1.463    0.000 {built-in method _struct.pack}
