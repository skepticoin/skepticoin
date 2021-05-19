from copy import deepcopy
import immutables
import pytest
from pathlib import Path

from skepticoin.humans import computer
from skepticoin.params import (
    DESIRED_TARGET_READJUSTMENT_TIMESPAN,
    INITIAL_TARGET,
    MAX_COINBASE_RANDOM_DATA_SIZE,
    SASHIMI_PER_COIN,
)
from skepticoin.coinstate import CoinState
from skepticoin.consensus import (
    calculate_new_target,
    construct_block_for_mining,
    construct_block_for_mining_genesis,
    construct_minable_summary_genesis,
    construct_minable_summary,
    construct_coinbase_transaction,
    construct_pow_evidence,
    get_block_subsidy,
    get_transaction_fee,
    validate_non_coinbase_transaction_by_itself,
    validate_coinbase_transaction_by_itself,
    validate_block_header_by_itself,
    validate_block_by_itself,
    # validate_non_coinbase_transaction_in_coinstate,
    ValidationError,
    ValidateBlockError,
    ValidateBlockHeaderError,
    ValidateTransactionError,
    ValidatePOWError,
)
from skepticoin.signing import SECP256k1PublicKey, SECP256k1Signature, SignableEquivalent
from skepticoin.datatypes import Transaction, OutputReference, Input, Output, Block, BlockHeader


CHAIN_TESTDATA_PATH = Path(__file__).parent.joinpath("testdata/chain")

example_public_key = SECP256k1PublicKey(b'x' * 64)


def _read_chain_from_disk(max_height):
    coinstate = CoinState.zero()

    for file_path in sorted(CHAIN_TESTDATA_PATH.iterdir()):
        height = int(file_path.name.split("-")[0])
        if height > max_height:
            return coinstate

        block = Block.stream_deserialize(open(file_path, 'rb'))
        coinstate = coinstate.add_block_no_validation(block)

    return coinstate


def get_example_genesis_block():
    # an example (valid) genesis block, but not the one from the actual Skepticoin blockchain.
    return Block.deserialize(computer(
        """000000000000000000000000000000000000000000000000000000000000000000008278968af4bd613aa24a5ccd5280211b3101e3"""
        """ff62621bb11500509d1bbe2a956046240b0100000000000000000000000000000000000000000000000000000000000000000000d7"""
        """38f2c472180cb401f650b12be96ec25bfd9b4e9908c6c9089d9bf26401646f87000000000000000000000000000000000000000000"""
        """0000000000000000000000077a14cfbe21d47f367f23f9a464c765541b1b07bef9f5a95901e0bffe3a1a2f01000100000000000000"""
        """000000000000000000000000000000000000000000000000000000000001000000000001000000012a05f200027878787878787878"""
        """7878787878787878787878787878787878787878787878787878787878787878787878787878787878787878787878787878787878"""
        """787878"""))


def test_calculate_new_target():
    assert calculate_new_target(INITIAL_TARGET, DESIRED_TARGET_READJUSTMENT_TIMESPAN)[:4] == b'\x01\x00\x00\x00'

    assert calculate_new_target(INITIAL_TARGET, DESIRED_TARGET_READJUSTMENT_TIMESPAN * 2)[:4] == b'\x02\x00\x00\x00'
    assert calculate_new_target(INITIAL_TARGET, DESIRED_TARGET_READJUSTMENT_TIMESPAN // 2)[:4] == b'\x00\x80\x00\x00'


def test_construct_minable_summary():
    summary = construct_minable_summary_genesis([
        construct_coinbase_transaction(0, [], immutables.Map(), b"Political statement goes here", example_public_key)
    ], 1231006505, 0)

    summary.serialize()
    # so far... just checking that this doesn't crash :-)


def test_construct_pow_evidence_genesis_block():
    # separate from test_construct_pow_evidence_block_6, because genesis block has no chain sampling (there is no chain)
    coinstate = CoinState.empty()

    transactions = [
        construct_coinbase_transaction(0, [], immutables.Map(), b"Political statement goes here", example_public_key),
    ]

    summary = construct_minable_summary_genesis(transactions, 1231006505, 0)

    evidence = construct_pow_evidence(coinstate, summary, 0, transactions)
    evidence.serialize()
    # no assertions here, just checking that this doesn't crash :-)


def test_construct_pow_evidence_non_genesis_block():
    coinstate = _read_chain_from_disk(5)

    transactions = [
        construct_coinbase_transaction(0, [], immutables.Map(), b"Political statement goes here", example_public_key),
    ]

    summary = construct_minable_summary(coinstate, transactions, 1231006505, 0)

    evidence = construct_pow_evidence(coinstate, summary, coinstate.head().height + 1, transactions)
    evidence.serialize()
    # no assertions here, just checking that this doesn't crash :-)


def test_construct_block_for_mining_no_non_coinbase_transactions():
    coinstate = _read_chain_from_disk(5)

    block = construct_block_for_mining(
        coinstate, [], example_public_key, 1231006505, b'skepticoin is digital bitcoin', 1234)

    assert 6 == block.height
    assert 1 == len(block.transactions)
    assert example_public_key == block.transactions[0].outputs[0].public_key
    assert 1231006505 == block.timestamp
    assert b'skepticoin is digital bitcoin' == block.transactions[0].inputs[0].signature.signature
    assert 1234 == block.nonce


def test_construct_block_for_mining_with_non_coinbase_transactions():
    coinstate = _read_chain_from_disk(5)

    transactions = [Transaction(
        inputs=[Input(
            OutputReference(coinstate.at_head.block_by_height[0].transactions[0].hash(), 0),
            SECP256k1Signature(b'y' * 64),
        )],
        outputs=[Output(9 * SASHIMI_PER_COIN, example_public_key)],
    )]

    block = construct_block_for_mining(
        coinstate, transactions, example_public_key, 1231006505, b'skepticoin is digital bitcoin', 1234)

    assert 6 == block.height
    assert 2 == len(block.transactions)
    assert 11 * SASHIMI_PER_COIN == block.transactions[0].outputs[0].value  # 10 mined + 1 fee
    assert example_public_key == block.transactions[0].outputs[0].public_key
    assert 1231006505 == block.timestamp
    assert b'skepticoin is digital bitcoin' == block.transactions[0].inputs[0].signature.signature
    assert 1234 == block.nonce


def test_validate_non_coinbase_transaction_by_itself_no_inputs():
    transaction = Transaction(
        inputs=[],
        outputs=[Output(30, example_public_key)],
    )

    with pytest.raises(ValidateTransactionError, match=".*No inputs.*"):
        validate_non_coinbase_transaction_by_itself(transaction)


def test_validate_non_coinbase_transaction_by_itself_no_outputs():
    transaction = Transaction(
        inputs=[Input(
            OutputReference(b'a' * 32, 1),
            SECP256k1Signature(b'y' * 64),
        )],
        outputs=[],
    )

    with pytest.raises(ValidateTransactionError, match=".*No outputs.*"):
        validate_non_coinbase_transaction_by_itself(transaction)


def test_validate_non_coinbase_transaction_by_itself_max_size():
    transaction = Transaction(
        inputs=[Input(
            OutputReference(b'a' * 32, 1),
            SECP256k1Signature(b'y' * 64),
        )] * 30_000,
        outputs=[Output(30, example_public_key)]
    )

    with pytest.raises(ValidateTransactionError, match=".*MAX_BLOCK_SIZE.*"):
        validate_non_coinbase_transaction_by_itself(transaction)


def test_validate_non_coinbase_transaction_by_itself_max_total_output():
    transaction = Transaction(
        inputs=[Input(
            OutputReference(b'a' * 32, 1),
            SECP256k1Signature(b'y' * 64),
        )],
        outputs=[Output(21_000_000 * SASHIMI_PER_COIN, example_public_key)]
    )

    with pytest.raises(ValidationError, match=".out of range.*"):
        validate_non_coinbase_transaction_by_itself(transaction)


def test_validate_non_coinbase_transaction_by_itself_no_duplicate_output_references():
    transaction = Transaction(
        inputs=[Input(
            OutputReference(b'a' * 32, 1),
            SECP256k1Signature(b'y' * 64),
        )] * 2,
        outputs=[Output(30, example_public_key)]
    )

    with pytest.raises(ValidateTransactionError, match=".*output_reference referenced more than once.*"):
        validate_non_coinbase_transaction_by_itself(transaction)


def test_validate_non_coinbase_transaction_by_itself_is_not_coinbase():
    transaction = Transaction(
        inputs=[Input(
            OutputReference(b'\x00' * 32, 0),
            SECP256k1Signature(b'y' * 64),
        )],
        outputs=[Output(30, example_public_key)]
    )

    with pytest.raises(ValidateTransactionError, match=".*null-reference in non-coinbase transaction.*"):
        validate_non_coinbase_transaction_by_itself(transaction)


def test_validate_non_coinbase_transaction_by_itself():
    transaction = Transaction(
        inputs=[Input(
            OutputReference(b'a' * 32, 1),
            SignableEquivalent(),
        )],
        outputs=[Output(30, example_public_key)]
    )

    with pytest.raises(ValidateTransactionError, match=".*Non-signature Signature class used.*"):
        validate_non_coinbase_transaction_by_itself(transaction)


def test_validate_signature_for_spend():
    # before anything: create sign_for_spend
    pass  # TODO


def test_get_transaction_fee():
    public_key = SECP256k1PublicKey(b'x' * 64)

    previous_transaction_hash = b'a' * 32

    unspent_transaction_outs = immutables.Map({
        OutputReference(previous_transaction_hash, 0): Output(40, public_key),
        OutputReference(previous_transaction_hash, 1): Output(34, public_key),
    })

    transaction = Transaction(
        inputs=[Input(
            OutputReference(previous_transaction_hash, 1),
            SECP256k1Signature(b'y' * 64),
        )],
        outputs=[Output(30, public_key)]
    )

    assert get_transaction_fee(transaction, unspent_transaction_outs) == 34 - 30  # 4


def test_get_block_fees():
    pass  # TODO


def test_get_block_subsidy():
    assert get_block_subsidy(0) == 10 * SASHIMI_PER_COIN
    assert get_block_subsidy(1_049_999) == 10 * SASHIMI_PER_COIN
    assert get_block_subsidy(1_050_000) == 5 * SASHIMI_PER_COIN
    assert get_block_subsidy(31_499_999) == 1
    assert get_block_subsidy(31_500_000) == 0


def _get_example_coinbase_transaction():
    height = 123
    non_coinbase_transactions = []
    unspent_transaction_outs = immutables.Map()
    miner_public_key = b'x' * 32
    random_data = b"No need to get all political here"
    return construct_coinbase_transaction(
        height, non_coinbase_transactions, unspent_transaction_outs, random_data, miner_public_key)


def test_validate_coinbase_transaction_by_itself_for_valid_coinbase():
    cb = _get_example_coinbase_transaction()
    validate_coinbase_transaction_by_itself(cb)


def test_validate_coinbase_transaction_by_itself_exactly_1_input():
    cb = _get_example_coinbase_transaction()
    cb.inputs.append(deepcopy(cb.inputs[0]))

    with pytest.raises(ValidateTransactionError, match=".*1 input.*"):
        validate_coinbase_transaction_by_itself(cb)


def test_validate_coinbase_transaction_by_itself_reference_real_output():
    cb = _get_example_coinbase_transaction()
    cb.inputs[0].output_reference = OutputReference(b'c' * 32, 4)

    with pytest.raises(ValidateTransactionError, match=".*must create.*thin air.*"):
        validate_coinbase_transaction_by_itself(cb)


def test_validate_coinbase_transaction_by_itself_should_have_coinbasedata():
    cb = _get_example_coinbase_transaction()
    cb.inputs[0].signature = SECP256k1Signature(b'c' * 64)

    with pytest.raises(ValidateTransactionError, match=".*CoinbaseData.*"):
        validate_coinbase_transaction_by_itself(cb)


def test_validate_coinbase_transaction_by_itself_maximum_coinbasedata_size():
    cb = _get_example_coinbase_transaction()
    cb.inputs[0].signature.signature = b'x' * (MAX_COINBASE_RANDOM_DATA_SIZE + 1)

    with pytest.raises(ValidateTransactionError, match=".*MAX_COINBASE_RANDOM_DATA_SIZE.*"):
        validate_coinbase_transaction_by_itself(cb)


def test_validate_block_header_by_itself_no_errors():
    validate_block_header_by_itself(get_example_genesis_block().header, current_timestamp=1615209942)


def test_validate_block_header_by_itself_for_bad_pow():
    block = get_example_genesis_block()
    block.header.summary.nonce = 1
    with pytest.raises(ValidatePOWError):
        validate_block_header_by_itself(block.header, 1615209942)


def test_validate_block_header_by_itself_for_block_from_the_future():
    block = get_example_genesis_block()
    with pytest.raises(ValidateBlockHeaderError):
        validate_block_header_by_itself(block.header, block.header.summary.timestamp - 100)


def test_validate_block_by_itself_for_correct_block():
    validate_block_by_itself(get_example_genesis_block(), 1615209942)


def test_validate_block_by_itself_no_transactions():
    block = get_example_genesis_block()
    block.transactions = []

    with pytest.raises(ValidateBlockError, match=".*No transactions.*"):
        validate_block_by_itself(block, 1615209942)


def test_validate_block_by_itself_max_block_size(mocker):
    # work around get_block_fees... because we would need a coinstate w/ 50_000 unspent outputs to make it work.
    mocker.patch("skepticoin.consensus.get_block_fees", return_value=0)

    transactions = [
        Transaction(
            inputs=[Input(
                OutputReference(i.to_bytes(32, 'big'), 1),
                SECP256k1Signature(b'y' * 64),
            )],
            outputs=[Output(1, example_public_key)]
        ) for i in range(50_000)
    ]

    block = construct_block_for_mining_genesis(transactions, example_public_key, 1231006505, b'', 22)

    with pytest.raises(ValidateBlockError, match=".*MAX_BLOCK_SIZE.*"):
        validate_block_by_itself(block, 1615209942)


def test_validate_block_by_itself_invalid_coinbase_transaction():
    coinstate = CoinState.empty()

    transactions = [Transaction(
        inputs=[Input(
            OutputReference(b'x' * 32, 1),
            SECP256k1Signature(b'y' * 64),
        )],
        outputs=[Output(1, example_public_key)]
    )]

    summary = construct_minable_summary(coinstate, transactions, 1615209942, 39)
    evidence = construct_pow_evidence(coinstate, summary, 0, transactions)
    block = Block(BlockHeader(summary, evidence), transactions)

    with pytest.raises(ValidateTransactionError, match=".*thin air.*"):
        validate_block_by_itself(block, 1615209942)


def test_validate_block_by_itself_for_mismatched_heights():
    block = get_example_genesis_block()
    block.height = 1

    with pytest.raises(ValidateBlockError, match=".*height.*"):
        validate_block_by_itself(block, 1615209942)


def test_validate_block_by_itself_invalid_non_coinbase_transaction():
    pass


def test_validate_block_by_itself_no_duplicate_transactions():
    pass


def test_validate_block_by_itself_no_duplicate_output_references():
    pass


def test_validate_block_by_itself_incorrect_merkle_root_hash():
    pass


def test_validate_non_coinbase_transaction_in_coinstate_invalid_output_reference():
    # I started on the below, but the amount of setup is getting excessive... perhaps it's going to be easier to
    # express these tests when more mechanisms of _creation_ are available? we'll see
    '''
    previous_transaction_hash = b'a' * 32

    unspent_transaction_outs = immutables.Map()

    transaction = Transaction(
        inputs=[Input(
            OutputReference(previous_transaction_hash, 1),
            SECP256k1Signature(b'y' * 64),
        )],
        outputs=[Output(30, public_key)]
    )

    with pytest.raises(ValidateTransactionError, match=r".*does not exist.*") as e:
        validate_non_coinbase_transaction_in_coinstate

    '''


def test_validate_non_coinbase_transaction_in_coinstate_invalid_signature():
    pass  # TODO


def test_validate_non_coinbase_transaction_in_coinstate_overspending():
    pass  # TODO


def test_validate_non_coinbase_transaction_in_coinstate_valid():
    pass  # TODO
