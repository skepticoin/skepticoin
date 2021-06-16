from typing import Tuple
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

from .http_handler import HttpHandler
from .web_app_loader import WEB_APP_LOADER


class StatefulServices():

    def __init__(self) -> None:

        self.event_queue = ['Initializing']

        self.actions = {
            '/': self.web_app_loader,
            '/wallet': self.get_wallet,
            '/height': self.get_chain_height,
            '/event-stream': self.event_stream,
        }

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

    def event_stream(self, handler: HttpHandler) -> Tuple[int, str, str]:
        msg = self.event_queue.pop() if self.event_queue else 'Nothing Is Happening'
        return (200, 'text/event-stream', 'data: %s\n\n' % msg)

    def get_wallet(self, handler: HttpHandler) -> Tuple[int, str, str]:
        return (200, 'application/json', str(len(self.wallet.keypairs)))

    def get_chain_height(self, handler: HttpHandler) -> Tuple[int, str, str]:
        height = len(self.thread.local_peer.chain_manager.coinstate.block_by_hash)
        return (200, 'application/json', str(height))

    def web_app_loader(self, handler: HttpHandler) -> Tuple[int, str, str]:
        return (200, "text/html", WEB_APP_LOADER)
