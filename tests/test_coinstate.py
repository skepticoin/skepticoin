import immutables

from scepticoin.signing import CoinbaseData, SECP256k1PublicKey, SECP256k1Signature
from scepticoin.datatypes import Transaction, OutputReference, Input, Output
from scepticoin.coinstate import uto_apply_transaction, pkb_apply_transaction, PKBalance
from scepticoin.consensus import construct_reference_to_thin_air


def test_uto_apply_transaction_on_coinbase():
    public_key = SECP256k1PublicKey(b'x' * 64)

    output_0 = Output(40, public_key)
    output_1 = Output(34, public_key)

    unspent_transaction_outs = immutables.Map()

    transaction = Transaction(
        inputs=[Input(
            construct_reference_to_thin_air(),
            CoinbaseData(0, b'coinbase of the first block'),
        )],
        outputs=[output_0, output_1]
    )

    result = uto_apply_transaction(unspent_transaction_outs, transaction, is_coinbase=True)

    assert OutputReference(transaction.hash(), 0) in result
    assert OutputReference(transaction.hash(), 1) in result

    assert result[OutputReference(transaction.hash(), 0)] == output_0
    assert result[OutputReference(transaction.hash(), 1)] == output_1


def test_uto_apply_transaction_on_non_coinbase_transaction():
    public_key = SECP256k1PublicKey(b'x' * 64)

    output_0 = Output(40, public_key)
    output_1 = Output(34, public_key)
    output_2 = Output(30, public_key)

    previous_transaction_hash = b'a' * 32

    unspent_transaction_outs = immutables.Map({
        OutputReference(previous_transaction_hash, 0): output_0,
        OutputReference(previous_transaction_hash, 1): output_1,
    })

    transaction = Transaction(
        inputs=[Input(
            OutputReference(previous_transaction_hash, 1),
            SECP256k1Signature(b'y' * 64),
        )],
        outputs=[output_2]
    )

    result = uto_apply_transaction(unspent_transaction_outs, transaction, is_coinbase=False)

    assert OutputReference(previous_transaction_hash, 0) in result
    assert OutputReference(previous_transaction_hash, 1) not in result  # spent
    assert OutputReference(transaction.hash(), 0) in result

    assert result[OutputReference(previous_transaction_hash, 0)] == output_0
    assert result[OutputReference(transaction.hash(), 0)] == output_2


def test_pkb_apply_transaction_on_coinbase():
    public_key_0 = SECP256k1PublicKey(b'0' * 64)
    public_key_1 = SECP256k1PublicKey(b'1' * 64)

    output_0 = Output(40, public_key_0)
    output_1 = Output(34, public_key_1)

    unspent_transaction_outs = immutables.Map()
    public_key_balances = immutables.Map()

    transaction = Transaction(
        inputs=[Input(
            construct_reference_to_thin_air(),
            CoinbaseData(0, b'coinbase of the first block'),
        )],
        outputs=[output_0, output_1]
    )

    result = pkb_apply_transaction(unspent_transaction_outs, public_key_balances, transaction, is_coinbase=True)

    assert public_key_0 in result
    assert public_key_1 in result

    assert result[public_key_0].value == 40
    assert result[public_key_1].value == 34


def test_pkb_apply_transaction_on_non_coinbase_transaction():
    public_key_0 = SECP256k1PublicKey(b'\x00' * 64)
    public_key_1 = SECP256k1PublicKey(b'\x01' * 64)
    public_key_2 = SECP256k1PublicKey(b'\x02' * 64)

    output_0 = Output(40, public_key_0)
    output_1 = Output(34, public_key_1)
    output_3 = Output(66, public_key_1)
    final_output = Output(30, public_key_2)

    previous_transaction_hash = b'a' * 32

    unspent_transaction_outs = immutables.Map({
        OutputReference(previous_transaction_hash, 0): output_0,
        OutputReference(previous_transaction_hash, 1): output_1,
        OutputReference(previous_transaction_hash, 2): output_3,
    })

    public_key_balances = immutables.Map({
        public_key_0: PKBalance(0, []),
        public_key_1: PKBalance(100, [
            OutputReference(previous_transaction_hash, 1),
            OutputReference(previous_transaction_hash, 2),
        ]),
    })

    transaction = Transaction(
        inputs=[Input(
            OutputReference(previous_transaction_hash, 1),
            SECP256k1Signature(b'y' * 64),
        )],
        outputs=[final_output]
    )

    result = pkb_apply_transaction(unspent_transaction_outs, public_key_balances, transaction, is_coinbase=False)

    assert result[public_key_0].value == 0  # not referenced in the transaction under consideration
    assert result[public_key_0].output_references == []

    assert result[public_key_1].value == 100 - 34
    assert result[public_key_1].output_references == [OutputReference(previous_transaction_hash, 2)]

    assert result[public_key_2].value == 30  # the value of the transaction output
    assert result[public_key_2].output_references == [OutputReference(transaction.hash(), 0)]
