from ptpython import repl
import argparse

from scepticoin.__version__ import __version__
import scepticoin.datatypes

from .utils import (
    initialize_peers_file,
    create_chain_dir,
    read_chain_from_disk,
    open_or_init_wallet,
    start_networking_peer_in_background,
)


def configure(repl):
    # from https://github.com/prompt-toolkit/ptpython/blob/master/examples/ptpython_config/config.py

    # Ask for confirmation on exit.
    repl.confirm_exit = False

    # embedded in other applications.
    repl.title = "Scepticoin %s " % __version__


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--vi-mode", help="Vi mode", action="store_true")
    args = parser.parse_args()

    create_chain_dir()
    coinstate = read_chain_from_disk()
    wallet = open_or_init_wallet()
    initialize_peers_file()
    thread = start_networking_peer_in_background(coinstate)
    thread.local_peer.show_stats()

    print("Starting REPL, exit with exit()")
    try:
        locals = {
            'thread': thread,
            'local_peer': thread.local_peer,
            'show_stats': thread.local_peer.show_stats,
            'wallet': wallet,
            'get_coinstate': lambda: thread.local_peer.chain_manager.coinstate,
        }

        for attr in scepticoin.datatypes.__all__:
            locals[attr] = getattr(scepticoin.datatypes, attr)

        repl.embed(vi_mode=args.vi_mode, locals=locals, configure=configure)

    finally:
        print("Stopping networking thread")
        thread.stop()
        print("Waiting for networking thread to stop")
        thread.join()
