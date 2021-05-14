import traceback

from .utils import (
    initialize_peers_file,
    create_chain_dir,
    read_chain_from_disk,
    open_or_init_wallet,
    start_networking_peer_in_background,
    configure_logging_from_args,
    DefaultArgumentParser,
)


class EverythingIsNone:
    def __getattr__(self, attr):
        return None


def main():
    parser = DefaultArgumentParser()
    parser.add_argument("script_file")
    args = parser.parse_args()
    configure_logging_from_args(args)

    create_chain_dir()
    coinstate = read_chain_from_disk()
    wallet = open_or_init_wallet()
    initialize_peers_file()
    thread = start_networking_peer_in_background(args, coinstate)
    thread.local_peer.show_stats()

    try:
        globals = {
            'thread': thread,
            'wallet': wallet,
            'get_coinstate': lambda: thread.local_peer.chain_manager.coinstate,
        }
        try:
            exec(open(args.script_file, 'r').read(), globals)
        except BaseException:
            print(traceback.format_exc())

    finally:
        print("Stopping networking thread")
        thread.stop()
        print("Waiting for networking thread to stop")
        thread.join()
        print("Done; waiting for Python-exit")
