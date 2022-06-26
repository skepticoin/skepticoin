from skepticoin.wallet import Wallet
from threading import Thread

from skepticoin.scripts.utils import (
    open_or_init_wallet,
    create_chain_dir,
    read_chain_from_disk,
    configure_logging_from_args,
    start_networking_peer_in_background,
    check_for_fresh_chain,
    DefaultArgumentParser,
)


class SkepticoinService():

    def __init__(self) -> None:

        self.event_queue = ['Initializing']

        initThread = Thread(target=lambda: self.run())
        initThread.start()

    def run(self) -> None:

        self.event_queue.append('Doing some busywork')
        parser = DefaultArgumentParser()
        args = parser.parse_args()
        configure_logging_from_args(args)

        self.event_queue.append('Creating chain dir')
        create_chain_dir()

        self.event_queue.append('Reading chain from disk')
        coinstate = read_chain_from_disk()

        self.event_queue.append('Reading wallet')
        self.wallet: Wallet = open_or_init_wallet()

        # start our own peer so the GUI can have fresh blockchain
        self.thread = start_networking_peer_in_background(args, coinstate)

        self.event_queue.append('Waiting for Fresh Chain')
        check_for_fresh_chain(self.thread)
        self.event_queue.append("Chain up to date")
