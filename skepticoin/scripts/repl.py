import os

from ptpython.entry_points.run_ptpython import get_config_and_history_file
from ptpython.repl import PythonRepl, embed, run_config

import skepticoin.datatypes
import skepticoin.networking.messages
import skepticoin.signing
import skepticoin.humans
from skepticoin.params import SASHIMI_PER_COIN
from skepticoin.scripts.utils import (
    configure_logging_from_args,
    check_chain_dir,
    read_chain_from_disk,
    open_or_init_wallet,
    start_networking_peer_in_background,
    DefaultArgumentParser,
)
from .version import __version__


class EverythingIsNone:
    def __getattr__(self, attr: str) -> None:
        return None


def main() -> None:
    config_file, history_file = get_config_and_history_file(EverythingIsNone())

    parser = DefaultArgumentParser()
    parser.add_argument("--vi-mode", help="Vi mode", action="store_true")
    args = parser.parse_args()
    configure_logging_from_args(args)

    check_chain_dir()
    coinstate = read_chain_from_disk()
    wallet = open_or_init_wallet()
    thread = start_networking_peer_in_background(args, coinstate)
    thread.local_peer.show_stats()

    print("Starting REPL, exit with exit()")
    try:
        globals = {
            'thread': thread,
            'local_peer': thread.local_peer,
            'show_stats': thread.local_peer.show_stats,
            'wallet': wallet,
            'get_coinstate': lambda: thread.local_peer.chain_manager.coinstate,
            'SASHIMI_PER_COIN': SASHIMI_PER_COIN,
        }

        for module in [skepticoin.datatypes, skepticoin.networking.messages, skepticoin.signing, skepticoin.humans]:
            for attr in module.__all__:  # type: ignore
                globals[attr] = getattr(module, attr)

        def configure(repl: PythonRepl) -> None:
            if os.path.exists(config_file):
                run_config(repl, config_file)
            else:
                # from https://github.com/prompt-toolkit/ptpython/blob/master/examples/ptpython_config/config.py
                # Ask for confirmation on exit.
                repl.confirm_exit = False

            # embedded in other applications.
            repl.title = "Skepticoin %s " % __version__

        embed(
            vi_mode=args.vi_mode,
            globals=globals,
            configure=configure,
            history_filename=history_file,
            patch_stdout=True,
        )

    finally:
        print("Stopping networking thread")
        thread.stop()
        print("Waiting for networking thread to stop")
        thread.join()
        print("Done; waiting for Python-exit")
