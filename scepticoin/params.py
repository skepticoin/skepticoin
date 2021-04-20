SASHIMI_PER_COIN = 100_000_000  # bitcoin calls this (perhaps somewhat too) simply "COIN"

# As is customary in the alt-coin sphere, we mess with the Bitcoin params a bit in order to generate an air of
# uniqueness. Ahum, I meant to say that the following parameters have been carefully chosen to match Bitcoin's total
# supply of money (remember: 1 scepticoin == 1 btc). However, we have made the block duration significantly shorter to
# provide a more interactive experience.

FIVE = (10 // 2)  # every 2 minutes. bitcoin has this at 10, so we change the params below with a factor of FIVE
DESIRED_BLOCK_TIMESPAN = 10 * 60 // FIVE
BLOCKS_BETWEEN_TARGET_READJUSTMENT = 2016 * FIVE
DESIRED_TARGET_READJUSTMENT_TIMESPAN = BLOCKS_BETWEEN_TARGET_READJUSTMENT * DESIRED_BLOCK_TIMESPAN  # every 2 weeks

INITIAL_SUBSIDY = 50 * SASHIMI_PER_COIN // FIVE
SUBSIDY_HALVING_INTERVAL = 210_000 * FIVE  # hype train departs every 4 years

MAX_BLOCK_SIZE = 1_000_000 // FIVE
MAX_COINBASE_RANDOM_DATA_SIZE = 200

# The total amount of money can be deduced from the halving algorithm but is put here as a constant; for bitcoin it is
# often said to be "21 million" but is actually 2_099_999_997_690_000 satoshi. Because of rounding differences there
# will be slightly fewer sashimi. The only logical conclusion is that scepticoin is slightly more valuable (deflation!)
# Note that this fits in 48 bits (and therefore easily in 8 bytes).
MAX_SASHIMI = 2_099_999_986_350_000

# this is the awesome script to determine this value:
"""
>>> total_coin = 0
... subsidy = 10 * 100_000_000
... while subsidy > 0:
...     total_coin += 5 * 210_000 * subsidy
...     subsidy = subsidy // 2
...     print(total_coin, subsidy)
"""

# We start with an arbitrarily low target; recalibration will follow soon anyway.
INITIAL_TARGET = (1 << (8 * 31)).to_bytes(length=32, byteorder='big')

# bitcoin, and many of its clones, actually allow for blocks to be mined up to 2 hours into the future. The reason given
# is that it's impossible to synchronize clocks in distributed networks. True as that may be, surely it's not hard to
# synchronize them "mostly correctly"? i.e. in the couple-of-seconds range? The constant below should be plenty.
MAX_FUTURE_BLOCK_TIME = 30


# POW Evidence
CHAIN_SAMPLE_COUNT = 8
CHAIN_SAMPLE_SIZE = 4
CHAIN_SAMPLE_TOTAL_SIZE = CHAIN_SAMPLE_COUNT * CHAIN_SAMPLE_SIZE
