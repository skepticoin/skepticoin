import immutables

from .humans import human, computer
from .params import (
    MAX_SASHIMI, MAX_BLOCK_SIZE, MAX_FUTURE_BLOCK_TIME, MAX_COINBASE_RANDOM_DATA_SIZE,
    BLOCKS_BETWEEN_TARGET_READJUSTMENT, DESIRED_TARGET_READJUSTMENT_TIMESPAN, SUBSIDY_HALVING_INTERVAL, INITIAL_SUBSIDY,
    CHAIN_SAMPLE_TOTAL_SIZE, CHAIN_SAMPLE_COUNT, CHAIN_SAMPLE_SIZE, INITIAL_TARGET
)
from .serialization import serialize_list
from .signing import CoinbaseData
from .merkletree import get_merkle_root
from .datatypes import OutputReference, Input, Output, Transaction, BlockSummary, PowEvidence, BlockHeader, Block
from .hash import scrypt, blake2
from .pow import select_n_k_length_slices_from_chain
from .coinstate import CoinState
from .cheating import KNOWN_HASHES, MAX_KNOWN_HASH_HEIGHT


# ## Section: Shared between Construction & Validation

def calc_merkle_root_hash(transactions):
    return get_merkle_root([transaction.hash() for transaction in transactions])


def calc_target(coinstate, height, current_timestamp, previous_block):
    if height % BLOCKS_BETWEEN_TARGET_READJUSTMENT == 0:
        interval_start_height = height - BLOCKS_BETWEEN_TARGET_READJUSTMENT
        interval_start_block = coinstate.block_by_height_by_hash[previous_block.hash()][interval_start_height]
        time_passed = current_timestamp - interval_start_block.timestamp
        return calculate_new_target(previous_block.target, time_passed)

    return previous_block.target


# ## Section: Construction of new Blocks

def construct_minable_summary_genesis(transactions, current_timestamp, nonce):
    return BlockSummary(
        height=0,
        previous_block_hash=b'\x00' * 32,
        merkle_root_hash=calc_merkle_root_hash(transactions),
        timestamp=current_timestamp,
        target=INITIAL_TARGET,
        nonce=nonce,
    )


def construct_minable_summary(coinstate, transactions, current_timestamp, nonce):
    if coinstate.current_chain_hash is None:
        return construct_minable_summary_genesis(transactions, current_timestamp, nonce)

    previous_block = coinstate.head()
    height = previous_block.height + 1
    return BlockSummary(
        height=height,
        previous_block_hash=coinstate.current_chain_hash,
        merkle_root_hash=calc_merkle_root_hash(transactions),
        timestamp=current_timestamp,
        target=calc_target(coinstate, height, current_timestamp, previous_block),
        nonce=nonce,
    )


def get_transaction_fee(transaction, unspent_transactions):
    """Money not explicitly claimed in a transaction will be available as a fee for the miner"""
    # should be called on valid transactions only (i.e. unspent output exists, no overspending)

    total_input_value = sum(
        unspent_transactions[input.output_reference].value
        for input in transaction.inputs
    )

    total_output_value = sum(output.value for output in transaction.outputs)

    return total_input_value - total_output_value


def get_block_fees(non_coinbase_transactions, unspent_transaction_outs):
    # Because intra-block cross-transaction-spending is illegal, no need to manipulate refetch unspent_transaction_outs
    return sum(get_transaction_fee(transaction, unspent_transaction_outs) for transaction in non_coinbase_transactions)


def get_block_subsidy(height):
    halvings = height // SUBSIDY_HALVING_INTERVAL

    if halvings >= 64:
        return 0

    return INITIAL_SUBSIDY // (2 ** halvings)


def construct_reference_to_thin_air():
    return OutputReference(b'\x00' * 32, 0)


def construct_coinbase_transaction(height, other_transactions, unspent_transaction_outs, signature, miner_public_key):
    subsidy = get_block_subsidy(height)
    fees = get_block_fees(other_transactions, unspent_transaction_outs)

    coinbase_data = CoinbaseData(
        height=height,
        signature=signature,
    )

    input = Input(
        output_reference=construct_reference_to_thin_air(),
        signature=coinbase_data,
    )

    output = Output(
        value=subsidy + fees,
        public_key=miner_public_key,
    )

    return Transaction(inputs=[input], outputs=[output])


def construct_pow_evidence(coinstate, summary, current_height, transactions):
    # Part 1 of the POW is to run scrypt. We put the most expensive operation first in an attempt to "up the ante"
    summary_hash = scrypt(summary.serialize(), current_height.to_bytes(8, byteorder='big'))

    # Part 2 of the POW is to prove that you have fast access to the whole blockchain. This is to help actual full nodes
    # vis-a-vis opportunistic miners.
    if current_height == 0:
        # in the genesis block we can't sample from the chain yet
        chain_sample = b'\00' * CHAIN_SAMPLE_TOTAL_SIZE
    else:
        get_block_by_height = lambda h: coinstate.block_by_height_by_hash[summary.previous_block_hash][h]  # noqa

        chain_sample = select_n_k_length_slices_from_chain(
            summary_hash, current_height, get_block_by_height, CHAIN_SAMPLE_COUNT, CHAIN_SAMPLE_SIZE)

    serialized_transactions = serialize_list(transactions)

    # Part 3 of the POW is to prove that the machine doing the work had access to the full list of transactions that
    # will be included in the block. The scenario this might guard against is that of malevolent parties renting mining
    # power to double-spend and/or mining pools gaining too much power and using it in ways that the members of the pool
    # would not agree to if they had seen the transactions.

    # This is a deviation from Bitcoin, in which the fixed length of the thing-to-mine is promoted as a feature, because
    # it does not create an incentive for miners to keep blocks short. To which we say: [1] why is it bad if there is at
    # least some incentive to keep blocks short, since this benefits the whole network? [2] we use a hashing algo that
    # is very fast in comparison to the main hashing algo (scrypt, above). We know this, because we spent 5 minutes
    # googling "fast cryptographic hash" and then picked the one which has native Python support. On 10MB blocks (many
    # times our actual block size) this hash runs in 0.02s on the developer's personal laptop (science!)
    block_hash = blake2(summary_hash + chain_sample + serialized_transactions)

    return PowEvidence(
        summary_hash=summary_hash,
        chain_sample=chain_sample,
        block_hash=block_hash,
    )


def construct_block_for_mining_genesis(
        non_coinbase_transactions, miner_public_key, current_timestamp, random_data, nonce):

    coinstate = CoinState.empty()
    current_height = 0

    unspent_transaction_outs = immutables.Map()

    coinbase_transaction = construct_coinbase_transaction(
        current_height, non_coinbase_transactions, unspent_transaction_outs, random_data, miner_public_key)

    transactions = [coinbase_transaction] + non_coinbase_transactions

    summary = construct_minable_summary(coinstate, transactions, current_timestamp, nonce)
    evidence = construct_pow_evidence(coinstate, summary, current_height, transactions)
    return Block(BlockHeader(summary, evidence), transactions)


def construct_block_for_mining(
        coinstate, non_coinbase_transactions, miner_public_key, current_timestamp, random_data, nonce):

    previous_block = coinstate.head()
    current_height = previous_block.height + 1

    unspent_transaction_outs = coinstate.unspent_transaction_outs_by_hash[coinstate.current_chain_hash]

    coinbase_transaction = construct_coinbase_transaction(
        current_height, non_coinbase_transactions, unspent_transaction_outs, random_data, miner_public_key)

    transactions = [coinbase_transaction] + non_coinbase_transactions

    summary = construct_minable_summary(coinstate, transactions, current_timestamp, nonce)
    evidence = construct_pow_evidence(coinstate, summary, current_height, transactions)
    return Block(BlockHeader(summary, evidence), transactions)

    # what would be nice to be able to verify independenly?
    # 1. calculation of summary_hash. (at cost of running scrypt once on the summary)
    # 2. calculation of any address byte individually (given the preceding bytes (if any) and a single block)
    # 3. calculation of bytes_from_block (given the current_block,


# ## Section: Validation


class ValidationError(Exception):
    pass


class ValidateTransactionError(ValidationError):
    pass


class ValidatePOWError(ValidationError):
    pass


class ValidateBlockHeaderError(ValidationError):
    pass


class ValidateBlockError(ValidationError):
    pass


def validate_sashimi_range(value):
    if not (0 < value <= MAX_SASHIMI):
        raise ValidationError("Value out of range.")


def validate_non_coinbase_transaction_by_itself(transaction):
    """Do those Transaction checks that can be done outside of the context a blockchain"""

    if len(transaction.inputs) == 0:
        raise ValidateTransactionError("No inputs")

    if len(transaction.outputs) == 0:
        raise ValidateTransactionError("No outputs")

    # block size is an upper bound for transaction size; there is no separate constant.
    if len(transaction.serialize()) > MAX_BLOCK_SIZE:
        raise ValidateTransactionError("transaction > MAX_BLOCK_SIZE")

    total_transaction_output_value = 0
    for output in transaction.outputs:
        validate_sashimi_range(output.value)
        total_transaction_output_value += output.value
    validate_sashimi_range(total_transaction_output_value)

    # Check for duplicate inputs; "in theory" this is redundant because each transaction output can be spent only once,
    # which is checked in validate_non_coinbase_transaction_in_coinstate. Some redundancy in checking might be useful
    # though, and checking it here allows us to catch such duplications even without the context of a full chain.
    output_references = set()
    for input in transaction.inputs:
        if input.output_reference in output_references:
            raise ValidateTransactionError("Single output_reference referenced more than once in single transaction.")
        output_references.add(input.output_reference)

    for input in transaction.inputs:
        if input.output_reference.references_thin_air():
            raise ValidateTransactionError("Coinbase-like null-reference in non-coinbase transaction.")

        if input.signature.is_not_signature():
            # as elsewhere: "in theory" this is redundant, because such a signature will never validate an output
            # anyway. checking it here allows us to catch such duplications even without the context of a full chain.
            raise ValidateTransactionError("Non-signature Signature class used where a real one is expected.")


def validate_signature_for_spend(input, previous_output, transaction):
    message = transaction.signable_equivalent().serialize()
    if not input.signature.validate(previous_output.public_key, message):
        raise ValidateTransactionError("Wrong signature for claimed output")


def validate_coinbase_transaction_by_itself(transaction):
    if not len(transaction.inputs) == 1:
        raise ValidateTransactionError("Coinbase transaction should have precisely 1 input")

    if not transaction.inputs[0].output_reference.references_thin_air():
        raise ValidateTransactionError("Coinbase must create its value out of thin air")

    if not isinstance(transaction.inputs[0].signature, CoinbaseData):
        raise ValidateTransactionError("A coinbase transaction should have CoinbaseData")

    if len(transaction.inputs[0].signature.signature) > MAX_COINBASE_RANDOM_DATA_SIZE:
        raise ValidateTransactionError("Random data > MAX_COINBASE_RANDOM_DATA_SIZE")


def validate_proof_of_work(hash, target):
    # N.B. just the final hash... without examining the evidence!

    if hash >= target:
        raise ValidatePOWError("hash >= target")


def validate_block_header_by_itself(block_header, current_timestamp):
    validate_proof_of_work(block_header.hash(), block_header.summary.target)

    if block_header.summary.timestamp > current_timestamp + MAX_FUTURE_BLOCK_TIME:
        raise ValidateBlockHeaderError("Block timestamp in the future")


def validate_no_duplicate_transactions(transactions):
    seen_transactions = set()
    for transaction in transactions:
        if transaction in seen_transactions:
            raise ValidateTransactionError("Duplicate transaction.")
        seen_transactions.add(transaction)


def validate_no_duplicate_output_references_in_transactions(transactions):
    seen_output_references = set()
    for transaction in transactions:
        for input in transaction.inputs:
            if input.output_reference in seen_output_references:
                raise ValidateTransactionError("Duplicate output_reference.")
            seen_output_references.add(input.output_reference)


def validate_block_by_itself(block, current_timestamp):
    validate_block_header_by_itself(block.header, current_timestamp)

    if len(block.transactions) == 0:
        raise ValidateBlockError("No transactions in block")

    if len(block.serialize()) > MAX_BLOCK_SIZE:
        raise ValidateBlockError("Block > MAX_BLOCK_SIZE")

    coinbase_transaction = block.transactions[0]

    validate_coinbase_transaction_by_itself(coinbase_transaction)

    if coinbase_transaction.inputs[0].signature.height != block.height:
        raise ValidateBlockError("block.height != coinbase.height")

    for transaction in block.transactions[1:]:
        validate_non_coinbase_transaction_by_itself(transaction)

    # Check for duplicate transactions; "in theory" this is redundant because each transaction output can be spent only
    # once,  which is checked in validate_non_coinbase_transaction_in_coinstate. Additionally, we don't suffer and from
    # Bitcoin's faulty (auto-duplicating) merkle-tree vulnerability. However, better safe than checking it here allows
    # us to catch such duplications even without the context of a full chain.
    validate_no_duplicate_transactions(block.transactions[1:])

    # We need to do this here because we the spending check based on coinstate only looks at the initial coinstate of
    # the block (i.e. the spending inside blocks isn't reflected in that check)
    validate_no_duplicate_output_references_in_transactions(block.transactions[1:])

    if block.header.summary.merkle_root_hash != calc_merkle_root_hash(block.transactions):
        raise ValidateBlockError("Incorrect merkle_root_hash")


def validate_coinbase_transaction_in_coinstate(transaction, block, coinstate):
    previous_block = coinstate.block_by_hash[block.header.summary.previous_block_hash]
    previous_height = previous_block.height
    calculated_current_height = previous_height + 1

    if block.height != calculated_current_height:
        raise ValidateBlockHeaderError("Block's reported height incorrect.")

    unspent_transaction_outs = coinstate.unspent_transaction_outs_by_hash[block.header.summary.previous_block_hash]
    fees = get_block_fees(block.transactions[1:], unspent_transaction_outs)
    subsidy = get_block_subsidy(block.height)

    if sum(output.value for output in transaction.outputs) > fees + subsidy:
        raise ValidateTransactionError('Transaction overspending (Coinbase)')


def validate_non_coinbase_transaction_in_coinstate(transaction, at_hash, coinstate):
    # Note that unspent_transaction_outs is fetched only once here, reflecting the state at the beginning of the block;
    # the implication is that spending money from another transaction in the same block is illegal. Though I'm sure
    # there are theoretical advantages in allowing it, the extra complexity isn't worth it. This also means we have to
    # check elsewhere (validate_block_by_itself) that a singe block cannot contain 2 transactions with the same
    # transaction output.
    unspent_transaction_outs = coinstate.unspent_transaction_outs_by_hash[at_hash]

    total_input_value = 0

    for input in transaction.inputs:
        if input.output_reference not in unspent_transaction_outs:
            raise ValidateTransactionError("input's output_reference does not exist as an unspent out")

        previous_output = unspent_transaction_outs[input.output_reference]

        # bitcoin has the concept of COINBASE_MATURITY here; we don't reproduce that idea here, shifting the
        # responsibility to the clients. Reasoning: is spending of newly minted coins really that different from
        # spending newly acquired coins?

        validate_signature_for_spend(input, previous_output, transaction)

        total_input_value += previous_output.value

    if sum(output.value for output in transaction.outputs) > total_input_value:
        raise ValidateTransactionError('Transaction overspending')


def calculate_new_target(previous_target, actual_time_passed):
    i_previous_target = int.from_bytes(previous_target, byteorder='big', signed=False)

    # multiplications first to avoid loss of precision; integer arithmetic only to avoid float-weirdness.
    result = (i_previous_target * actual_time_passed) // DESIRED_TARGET_READJUSTMENT_TIMESPAN

    if result > pow(2, 32 * 8) - 1:
        result = pow(2, 32 * 8) - 1  # TBH we have bigger problems if the target has become "anything goes", but still..

    return result.to_bytes(32, byteorder='big', signed=False)


def validate_block_summary_in_coinstate(block_summary, coinstate):
    if block_summary.previous_block_hash not in coinstate.block_by_hash:
        raise ValidateBlockHeaderError("previous_block_hash unknown: %s" % human(block_summary.previous_block_hash))

    previous_block = coinstate.block_by_hash[block_summary.previous_block_hash]

    if block_summary.timestamp <= previous_block.timestamp:
        # A simplification w.r.t. bitcoin, which accepts so little about reality that it presumes time cannot be
        # synchronized with greater precision than 2 full hours.
        raise ValidateBlockHeaderError("Timestamps must be strictly increasing.")

    previous_height = previous_block.height
    calculated_current_height = previous_height + 1

    calculated_target = calc_target(coinstate, calculated_current_height, block_summary.timestamp, previous_block)

    if block_summary.target != calculated_target:
        raise ValidateBlockHeaderError("Block's reported target incorrect")


def validate_block_in_coinstate(block, coinstate):
    if block.height <= MAX_KNOWN_HASH_HEIGHT:
        if block.height in KNOWN_HASHES:
            if block.hash() != computer(KNOWN_HASHES[block.height]):
                raise ValidationError("No forks allowed before block %s" % MAX_KNOWN_HASH_HEIGHT)

        # all in-coinstate validation is skipped for such blocks; this may lead to invalid blocks being accepted in your
        # local coinstate, but never beyond one of the checkpoints from KNOWN_HASHES
        return

    validate_block_summary_in_coinstate(block.header.summary, coinstate)

    reconstructed_evidence = construct_pow_evidence(coinstate, block.header.summary, block.height, block.transactions)
    if block.header.pow_evidence != reconstructed_evidence:
        raise ValidateBlockError("POW Evidence incorrect")

    coinbase_transaction = block.transactions[0]
    validate_coinbase_transaction_in_coinstate(coinbase_transaction, block, coinstate)

    for transaction in block.transactions[1:]:
        validate_non_coinbase_transaction_in_coinstate(transaction, block.previous_block_hash, coinstate)
