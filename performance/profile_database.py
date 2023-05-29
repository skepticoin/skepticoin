# Compare the speed of some different ways of getting a chain index into memory.
# At the time of writing, version2 was suprisingly >10x faster than version1.
#
# Run with:
#   pytest -s ./performance/profile_get_chain.py

import cProfile
from typing import List
from skepticoin.blockstore import BlockStore

from skepticoin.humans import computer
from skepticoin.scripts.utils import DEFAULT_BLOCKSTORE_FILE_PATH

# this requires a recent big chain for meaningful results
blockstore = BlockStore(DEFAULT_BLOCKSTORE_FILE_PATH)

block_400k = computer('0009a644ee6486a419e935c97253c75001888837dd4c71f107c879df772bccbe')


def loader_version1(at_hash: bytes) -> List[int]:

    chain = [row[0] for row in blockstore.sql(
        """
        WITH RECURSIVE main_chain(block_id, block_hash, previous_block_hash) AS (
            SELECT block_id, block_hash, previous_block_hash
            FROM chain
            WHERE block_hash = ?
            UNION ALL
            SELECT c.block_id, c.block_hash, c.previous_block_hash
            FROM chain c
            JOIN main_chain mc ON mc.previous_block_hash = c.block_hash
            WHERE mc.previous_block_hash IS NOT NULL
        )
        SELECT block_id FROM main_chain ORDER BY block_id
        """, (at_hash,))]

    return chain


def loader_version2(at_hash: bytes) -> List[int]:

    all_forks = blockstore.sql(
        """select block_id, block_hash, previous_block_hash
           from chain
           where height <= 400000
           order by height desc"""
    )
    chain = []
    next = at_hash
    for row in all_forks:
        if row[1] == next:
            chain.append(row[0])
            next = row[2]
            if next is None:
                break
    return [i for i in reversed(chain)]


def all():
    v1 = loader_version1(block_400k)
    v2 = loader_version2(block_400k)
    assert v1 == v2


def test_main():

    with cProfile.Profile() as pr:
        pr.runcall(all)
        pr.print_stats(sort='cumulative')
