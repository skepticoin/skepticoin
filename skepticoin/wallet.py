from __future__ import annotations

import os
from typing import Dict, List, Mapping, Set, TextIO

import ecdsa
import json

from .coinstate import CoinState, PKBalance
from .humans import computer, human
from .signing import SECP256k1PublicKey, SECP256k1Signature
from .datatypes import Input, Transaction, Output, OutputReference


class AddressParseError(Exception):
    pass


class Wallet:
    def __init__(
        self,
        keypairs: Dict[bytes, bytes],
        unused_public_keys: List[bytes],
        public_key_annotations: Dict[bytes, str],
    ):
        self.keypairs = keypairs  # public => private

        self.unused_public_keys = unused_public_keys
        self.public_key_annotations = public_key_annotations

        self.spent_transaction_outputs: Set[
            OutputReference
        ] = set()  # TODO save to disk too at some point.

    def __repr__(self) -> str:
        return "Wallet w/ %s keypairs" % len(self.keypairs)

    @classmethod
    def empty(cls) -> Wallet:
        return cls({}, [], {})

    def __getitem__(self, public_key: bytes) -> bytes:
        return self.keypairs[public_key]

    def __contains__(self, public_key: bytes) -> bool:
        return public_key in self.keypairs

    def get_annotated_public_key(self, annotation: str) -> bytes:
        public_key = self.unused_public_keys.pop()
        self.public_key_annotations[public_key] = annotation
        return public_key

    def generate_key(self) -> None:
        sk = ecdsa.SigningKey.generate(curve=ecdsa.SECP256k1)
        private_key = sk.to_string()  # deceptive naming: to_string() actually returns a bytes object
        public_key = sk.verifying_key.to_string()
        self.keypairs[public_key] = private_key
        self.unused_public_keys.append(public_key)

    def generate_keys(self, n: int = 100) -> None:
        for _ in range(n):
            self.generate_key()

    def dump(self, f: TextIO) -> None:
        # The Simplest Thing That Could Possibly Work (though not the most secure)
        json.dump({
            "keypairs": {human(k): human(v) for (k, v) in self.keypairs.items()},
            "unused_public_keys": [human(e) for e in self.unused_public_keys],
            "public_key_annotations": {human(k): annotation for (k, annotation) in self.public_key_annotations.items()},
        }, f, indent=4)

    @classmethod
    def load(cls, f: TextIO) -> Wallet:
        d = json.load(f)

        return cls(
            keypairs={computer(k): computer(v) for (k, v) in d["keypairs"].items()},
            unused_public_keys=[computer(e) for e in d["unused_public_keys"]],
            public_key_annotations={computer(k): annotation for (k, annotation) in d["public_key_annotations"].items()},
        )

    def get_balance(self, coinstate: CoinState) -> int:
        return sum(
            coinstate.public_key_balances_by_hash[coinstate.current_chain_hash].get(  # type: ignore
                SECP256k1PublicKey(pk), PKBalance(0, [])).value
            for pk in self.keypairs.keys()
        )


def sign_transaction(
    wallet: Wallet,
    unspent_transaction_outs: Mapping[OutputReference, Output],
    transaction: Transaction,
) -> Transaction:
    message = transaction.signable_equivalent().serialize()

    signed_inputs = []
    for input in transaction.signable_equivalent().inputs:
        if input.output_reference not in unspent_transaction_outs:
            raise Exception("Attempting to sign invalid transaction")

        output = unspent_transaction_outs[input.output_reference]

        if not isinstance(output.public_key, SECP256k1PublicKey):
            raise Exception("No idea how to sign this thing")

        if output.public_key.public_key not in wallet:
            raise Exception("Can't sign this; no known private key in wallet")

        private_key = wallet[output.public_key.public_key]

        sk = ecdsa.SigningKey.from_string(private_key, curve=ecdsa.SECP256k1)

        signed_inputs.append(Input(
            output_reference=input.output_reference,
            signature=SECP256k1Signature(sk.sign(message)),
        ))

    return Transaction(
        inputs=signed_inputs,
        outputs=transaction.outputs,
    )


def create_spend_transaction(
    wallet: Wallet,
    coinstate: CoinState,
    value: int,
    miners_fee: int,
    output_public_key: SECP256k1PublicKey,
    change_address: SECP256k1PublicKey,
) -> Transaction:
    collected_value = 0
    inputs = []

    unspent_transaction_outs = coinstate.at_head.unspent_transaction_outs

    for public_key in wallet.keypairs.keys():
        if SECP256k1PublicKey(public_key) not in coinstate.at_head.public_key_balances:
            continue

        for output_reference in coinstate.at_head.public_key_balances[SECP256k1PublicKey(public_key)].output_references:
            if output_reference in wallet.spent_transaction_outputs:
                # in spent_transaction_outputs we keep track of those outputs that we've spent using this wallet (and
                # presumably broadcast) but which haven't made it into the chain yet.
                continue

            wallet.spent_transaction_outputs.add(output_reference)

            inputs.append(Input(output_reference, None))

            collected_value += unspent_transaction_outs[output_reference].value

            if collected_value >= value + miners_fee:
                outputs = [Output(value, output_public_key)]

                if collected_value != value + miners_fee:
                    outputs.append(Output(
                        collected_value - (value + miners_fee),
                        change_address,
                    ))

                return sign_transaction(wallet, unspent_transaction_outs, Transaction(inputs, outputs))

    raise Exception("Insufficient balance")


def save_wallet(wallet: Wallet) -> None:
    # This manual handling of files is sure to create wallet file corruption at one point or another... oh well,
    # reliving the bitcoin experience one mistake at a time.

    with open("wallet.json.new", 'w') as f:
        wallet.dump(f)

    os.replace("wallet.json.new", "wallet.json")


def is_valid_address(full_skepticoin_address: str) -> bool:
    try:
        parse_address(full_skepticoin_address)
        return True
    except AddressParseError:
        return False


def parse_address(full_skepticoin_address: str) -> bytes:
    if full_skepticoin_address[:3] != "SKE":
        raise AddressParseError()

    if full_skepticoin_address[-3:] != "PTI":
        raise AddressParseError()

    if len(full_skepticoin_address) != 3 + 128 + 3:
        raise AddressParseError()

    if not all(c in '0123456789abcdef' for c in full_skepticoin_address[3:-3]):
        raise AddressParseError()

    return computer(full_skepticoin_address[3:-3])
