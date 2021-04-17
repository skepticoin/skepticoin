import argparse

from ..humans import human

from .utils import open_or_init_wallet, save_wallet


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("annotation", help="Some text to help you remember a meaning for this receive address.")
    args = parser.parse_args()

    wallet = open_or_init_wallet()
    public_key = wallet.get_annotated_public_key(args.annotation)
    save_wallet(wallet)

    print("SCE" + human(public_key) + "PTI")
