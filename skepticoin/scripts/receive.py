from ..humans import human

from .utils import (
    open_or_init_wallet,
    save_wallet,
    configure_logging_from_args,
    DefaultArgumentParser,
)


def main():
    parser = DefaultArgumentParser()
    parser.add_argument("annotation", help="Some text to help you remember a meaning for this receive address.")
    args = parser.parse_args()
    configure_logging_from_args(args)

    wallet = open_or_init_wallet()
    public_key = wallet.get_annotated_public_key(args.annotation)
    save_wallet(wallet)

    print("SKE" + human(public_key) + "PTI")
