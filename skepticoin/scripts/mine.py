import os
from pathlib import Path
from decimal import Decimal
from datetime import datetime
import random
from skepticoin.datatypes import Block
from skepticoin.networking.threading import NetworkingThread
from skepticoin.coinstate import CoinState
from typing import Any, Dict

from skepticoin.params import SASHIMI_PER_COIN
from skepticoin.consensus import construct_block_for_mining
from skepticoin.signing import SECP256k1PublicKey
from skepticoin.wallet import Wallet, save_wallet
from skepticoin.utils import block_filename
from skepticoin.cheating import MAX_KNOWN_HASH_HEIGHT
from time import time
from multiprocessing import Process, Lock, Queue, synchronize
from .utils import (
    initialize_peers_file,
    create_chain_dir,
    read_chain_from_disk,
    open_or_init_wallet,
    start_networking_peer_in_background,
    check_for_fresh_chain,
    configure_logging_from_args,
    DefaultArgumentParser,
)


def run_miner(args: Any, wallet_lock: synchronize.Lock, queue: Queue, miner_id: int) -> None:
    miner = Miner(args, wallet_lock, queue, miner_id)
    miner()


class Miner:
    def __init__(self, args: Any, wallet_lock: synchronize.Lock, queue: Queue, miner_id: int) -> None:
        self.args = args
        self.wallet_lock = wallet_lock
        self.queue = queue
        self.miner_id = miner_id
        self.wallet: Wallet
        self.coinstate: CoinState
        self.thread: NetworkingThread

    def send_message(self, message_type: str, data: Any) -> None:
        message = (self.miner_id, message_type, data)
        self.queue.put(message)

    def prepare(self):
        configure_logging_from_args(self.args)

        create_chain_dir()
        self.coinstate = read_chain_from_disk()

        self.wallet_lock.acquire()
        self.wallet = open_or_init_wallet()
        self.wallet_lock.release()

        initialize_peers_file()
        self.thread = start_networking_peer_in_background(self.args, self.coinstate)
        self.thread.local_peer.show_stats()

        if check_for_fresh_chain(self.thread):
            self.thread.local_peer.show_stats()

        if self.thread.local_peer.chain_manager.coinstate.head().height <= MAX_KNOWN_HASH_HEIGHT:
            self.send_message("info", "Your blockchain is not just old, it is ancient; ABORTING")
            os.exit(0)

    def get_key_for_mined_block(self) -> bytes:
        self.wallet_lock.acquire()
        public_key = self.wallet.get_annotated_public_key("reserved for potentially mined block")
        save_wallet(self.wallet)
        self.wallet_lock.release()
        return public_key

    def get_balance(self) -> Decimal:
        self.wallet_lock.acquire()
        balance = self.wallet.get_balance(self.coinstate) / Decimal(SASHIMI_PER_COIN)
        self.wallet_lock.release()
        return balance

    def handle_mined_block(self, block: Block) -> None:
        self.coinstate = self.coinstate.add_block(block, int(time()))
        with open(Path('chain') / block_filename(block), 'wb') as f:
            f.write(block.serialize())

        self.send_message("found_block", block_filename(block))
        self.send_message("balance", self.get_balance())

        self.thread.local_peer.chain_manager.set_coinstate(self.coinstate)
        self.thread.local_peer.network_manager.broadcast_block(block)

    def __call__(self) -> None:
        self.prepare()
        self.send_message("start_balance", self.get_balance())
        self.send_message("info", "Starting mining: A repeat minter")

        try:
            public_key = self.get_key_for_mined_block()
            nonce = random.randrange(1 << 32)
            last_round_second = int(time())
            hashes = 0

            while True:
                current_second = int(time())

                if current_second > last_round_second:
                    self.send_message("hashes", (current_second, hashes))
                    last_round_second = current_second
                    hashes = 0

                self.coinstate, transactions = self.thread.local_peer.chain_manager.get_state()
                increasing_time = max(current_second, self.coinstate.head().timestamp + 1)

                block = construct_block_for_mining(
                    self.coinstate, transactions, SECP256k1PublicKey(public_key), increasing_time, b'', nonce)

                hashes += 1
                nonce = (nonce + 1) % (1 << 32)

                if block.hash() < block.target:
                    self.handle_mined_block(block)
                    public_key = self.get_key_for_mined_block()

        except KeyboardInterrupt:
            self.send_message("info", "KeyboardInterrupt")

        finally:
            self.send_message("info", "Stopping networking thread")
            self.thread.stop()

            self.send_message("info", "Waiting for networking thread to stop")
            self.thread.join()

            self.send_message("info", "Done; waiting for Python-exit")


def main() -> None:
    parser = DefaultArgumentParser()
    parser.add_argument('-n', default=1, type=int, help='number of miner instances')
    args = parser.parse_args()

    queue = Queue()
    wallet_lock = Lock()
    processes = []

    for i in range(args.n):
        if i > 0:
            args.dont_listen = True

        process = Process(target=run_miner, daemon=True, args=(args, wallet_lock, queue, i))
        process.start()
        processes.append(process)

    hash_stats: Dict[int, Dict[int, int]] = {}
    start_time = datetime.now()

    balance = 0
    start_balance = 0

    try:
        while True:
            miner_id, message_type, data = queue.get()

            if message_type == "hashes":
                timestamp, hashes = data

                if timestamp not in hash_stats:
                    hash_stats[timestamp] = {}

                hash_stats[timestamp][miner_id] = hashes

                current_time = int(time())

                # delete old hashing stats
                for ts, miner_stats in list(hash_stats.items()):
                    if ts < current_time and len(miner_stats) < args.n:
                        print(f"WARNING: Only got stats from {len(miner_stats)} "
                              f"of {args.n} processes at timestamp {timestamp}.")
                        del hash_stats[ts]

                if len(hash_stats[timestamp]) == args.n:
                    now = datetime.now()
                    now_str = now.strftime("%Y-%m-%d %H:%M:%S")
                    uptime = now - start_time
                    uptime_str = str(uptime).split(".")[0]

                    mined = balance - start_balance
                    total_hashes = sum(hash_stats[timestamp].values())
                    del hash_stats[timestamp]

                    mine_speed = (float(mined) / uptime.total_seconds()) * 60 * 60
                    print(f"{now_str} | uptime: {uptime_str} | {total_hashes:>3} hash/sec" +
                          f" | mined: {mined:>3} SKEPTI | {mine_speed:5.2f} SKEPTI/h")

            elif message_type == "balance":
                balance = data

            elif message_type == "start_balance":
                start_balance = data
                balance = data

            elif message_type == "found_block":
                print(f"miner {miner_id:2} found block: {data}")

            elif message_type == "info":
                print(f"miner {miner_id:2}: {data}")

            else:
                print(f"unhandled message_type {message_type} from {miner_id}, data={data}")

    except KeyboardInterrupt:
        pass
    finally:
        for process in processes:
            process.join()
