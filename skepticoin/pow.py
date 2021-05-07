"""
Proof of Waste... I mean Work

In general simplicity is one of the main goals in the Skepticoin codebase. The less smoke and mirrors, the more closely
we can observe the trick. Here we deviate from that approach somewhat, for the following reasons:

* We don't want 0.0000001% of the bitcoin/litecoin mining power to be enough to do a successful 51% attack on our coin.
  If we actually manage to make someone angry, better make them put in some work before they can attack us.
* The parameters of the POW algorithm were "carefully chosen" to favor regular Joes on their laptops over evil miners on
  ASICs. However, see https://ieeexplore.ieee.org/stamp/stamp.jsp?arnumber=8516911 for thoughts on how long that may
  last.
"""

from skepticoin.hash import sha256d


def select_block_height(input_hash, current_height):
    # we interpret the first 8 bytes of the input_hash as a number, and then modulo height. This should be enough for
    # the near future because (1 << 64) // (60 * 60 * 24 * 365) == 584_942_417_355 years if we use 1s blocks

    # current_height is the height of the block which hash we're mining/verifying

    base = int.from_bytes(input_hash[:8], byteorder='big', signed=False)
    return base % current_height


def select_block_slice(hash, serialized_block, length):
    # we interpret the next 4 bytes of the hash as a number, and then modulo block length. Support for up to 4GiB blocks

    base = int.from_bytes(hash[8:12], byteorder='big', signed=False)
    start = base % len(serialized_block)

    result = b""
    while len(result) < length:
        result += serialized_block[start:start + length - len(result)]
        start = 0

    return result


def select_slice_from_chain(input_hash, current_height, get_block_by_height, length):
    selected_block_height = select_block_height(input_hash, current_height)

    selected_block = get_block_by_height(selected_block_height)

    return select_block_slice(input_hash, selected_block.serialize(), length)


def select_n_k_length_slices_from_chain(starting_hash, current_height, get_block_by_height, n, k):
    result = []

    current_hash = starting_hash
    for i in range(n):
        b = select_slice_from_chain(current_hash, current_height, get_block_by_height, k)
        result.append(b)

        if i != n - 1:
            # presumed to be cheap. We also pick something different from scrypt, to be "multi hash"
            current_hash = sha256d(current_hash + b)

    return b"".join(result)
