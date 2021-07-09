from decimal import Decimal
from datetime import datetime, timedelta
import random
import traceback
from skepticoin.datatypes import Block, BlockHeader, BlockSummary, Transaction
from skepticoin.networking.threading import NetworkingThread
from skepticoin.coinstate import CoinState
from typing import Any, Callable, Dict, List, Tuple

from skepticoin.params import SASHIMI_PER_COIN
from skepticoin.consensus import (
    construct_block_pow_evidence_input,
    construct_pow_evidence_after_scrypt,
    construct_summary_hash,
)
from skepticoin.signing import SECP256k1PublicKey
from skepticoin.wallet import Wallet, save_wallet
from skepticoin.utils import block_filename
from skepticoin.cheating import MAX_KNOWN_HASH_HEIGHT
from time import time
from multiprocessing import Process, Queue
from skepticoin.scripts.utils import (
    check_chain_dir,
    read_chain_from_disk,
    open_or_init_wallet,
    start_networking_peer_in_background,
    wait_for_fresh_chain,
    configure_logging_from_args,
    DefaultArgumentParser,
)


def run_miner(args: Any, send_queue: Queue, recv_queue: Queue, miner_id: int) -> None:
    miner = Miner(args, send_queue, recv_queue, miner_id)
    miner()


class Miner:
    def __init__(self, args: Any, send_queue: Queue, recv_queue: Queue, miner_id: int) -> None:
        self.args = args
        self.send_queue = send_queue
        self.recv_queue = recv_queue
        self.miner_id = miner_id

    def send_message(self, message_type: str, data: Any) -> None:
        message = (self.miner_id, message_type, data)
        self.send_queue.put(message)

    def wait_for_message(self, expected_message_type: str) -> Any:
        message_type, data = self.recv_queue.get()

        if message_type != expected_message_type:
            print(f"WARNING: expected message type {expected_message_type}, got {message_type}")
            exit(1)

        return data

    def get_scrypt_input(self, nonce: int) -> Tuple[BlockSummary, int]:
        self.send_message("request_scrypt_input", nonce)
        summary, current_height = self.wait_for_message("scrypt_input")
        return summary, current_height

    def __call__(self) -> None:
        configure_logging_from_args(self.args)
        print(f"miner {self.miner_id}: starting a repeat minter")

        nonce = random.randrange(1 << 32)

        try:
            while True:
                summary, current_height = self.get_scrypt_input(nonce)
                summary_hash = construct_summary_hash(summary, current_height)
                self.send_message('scrypt_output', summary_hash)

                nonce = (nonce + 1) % (1 << 32)

        except KeyboardInterrupt:
            print(f"miner {self.miner_id} shutting down")


class MinerWatcher:
    def __init__(self) -> None:
        parser = DefaultArgumentParser()
        parser.add_argument('-n', default=1, type=int, help='number of miner instances')
        parser.add_argument('--quiet', action='store_true', help='do not print stats to the console every second')
        self.args = parser.parse_args()

        self.recv_queue: Queue = Queue()
        self.send_queues: List[Queue] = []
        self.processes: List[Process] = []

        self.hash_stats: Dict[int, int] = {}
        self.balance: Decimal = Decimal(0)
        self.start_balance: Decimal = Decimal(0)
        self.start_time: datetime
        self.wallet: Wallet
        self.coinstate: CoinState
        self.network_thread: NetworkingThread
        self.mining_args: Dict[int, Tuple[BlockSummary, int, List[Transaction]]] = {}
        self.public_key: bytes

    def __call__(self) -> None:
        configure_logging_from_args(self.args)

        check_chain_dir()
        self.coinstate = read_chain_from_disk()

        self.wallet = open_or_init_wallet()
        self.start_balance = self.wallet.get_balance(self.coinstate) / Decimal(SASHIMI_PER_COIN)
        self.balance = self.start_balance

        self.network_thread = start_networking_peer_in_background(self.args, self.coinstate)

        self.network_thread.local_peer.show_stats()

        wait_for_fresh_chain(self.network_thread)
        self.network_thread.local_peer.show_stats()

        if self.network_thread.local_peer.chain_manager.coinstate.head().height <= MAX_KNOWN_HASH_HEIGHT:
            print("Your blockchain is not just old, it is ancient; ABORTING")
            exit(1)

        self.public_key = self.wallet.get_annotated_public_key("reserved for potentially mined block")
        save_wallet(self.wallet)

        for miner_id in range(self.args.n):
            if miner_id > 0:
                self.args.dont_listen = True

            send_queue: Queue = Queue()
            process = Process(target=run_miner, daemon=True,
                              args=(self.args, self.recv_queue, send_queue, miner_id))
            process.start()
            self.processes.append(process)
            self.send_queues.append(send_queue)

        self.start_time = datetime.now() - timedelta(seconds=1)  # prevent negative uptime due to second rounding

        try:
            while True:
                queue_item: Tuple[int, str, Any] = self.recv_queue.get()
                self.handle_received_message(queue_item)

        except KeyboardInterrupt:
            pass

        except Exception:
            print("Error in MinerWatcher message loop: " + traceback.format_exc())

        finally:
            print("Restoring unused public key")
            self.wallet.restore_annotated_public_key(self.public_key, "reserved for potentially mined block")

            print("Stopping networking thread")
            self.network_thread.stop()

            print("Waiting for networking thread to stop")
            self.network_thread.join()

            for process in self.processes:
                process.join()

    def print_stats_line(self, timestamp: int) -> None:
        if self.args.quiet:
            return

        now = datetime.fromtimestamp(timestamp)
        now_str = now.strftime("%Y-%m-%d %H:%M:%S")

        uptime = now - self.start_time
        uptime_str = str(uptime).split(".")[0]

        mined = self.balance - self.start_balance
        hashes = self.hash_stats[timestamp]

        mine_speed = (float(mined) / uptime.total_seconds()) * 60 * 60

        n_peers = len(self.network_thread.local_peer.network_manager.get_active_peers())

        print(f"{now_str} | uptime: {uptime_str} | {hashes:>3} hash/sec" +
              f" | mined: {mined:>3} SKEPTI | {mine_speed:5.2f} SKEPTI/h" +
              f" | {n_peers:3d} peers")

    def send_message(self, miner_id: int, message_type: str, data: Any) -> None:
        self.send_queues[miner_id].put((message_type, data))

    def handle_received_message(self, queue_item: Tuple[int, str, Any]) -> None:
        miner_id, message_type, data = queue_item

        message_handlers: Dict[str, Callable[[int, Any], None]] = {
            "request_scrypt_input": self.handle_request_scrypt_input_message,
            "scrypt_output": self.handle_scrypt_output_message,
        }

        def handle_unknown_message(miner_id: int, data: Any) -> None:
            print(f"unhandled message_type {message_type} from {miner_id}, data={data}")

        handler = message_handlers.get(message_type, handle_unknown_message)
        handler(miner_id, data)

    def handle_request_scrypt_input_message(self, miner_id: int, data: int) -> None:
        nonce: int = data

        self.coinstate, transactions = self.network_thread.local_peer.chain_manager.get_state()
        increasing_time = max(int(time()), self.coinstate.head().timestamp + 1)

        summary, current_height, transactions = \
            construct_block_pow_evidence_input(self.coinstate, transactions, SECP256k1PublicKey(self.public_key),
                                               increasing_time, b'', nonce)

        self.mining_args[miner_id] = summary, current_height, transactions
        self.send_message(miner_id, "scrypt_input", (summary, current_height))

    def increment_hash_counter(self) -> None:
        timestamp = int(time())

        if timestamp not in self.hash_stats:

            # this is a new second: print and delete last stat(s)
            for ts in sorted(list(self.hash_stats.keys())):
                self.print_stats_line(ts)
                del self.hash_stats[ts]

            self.hash_stats[timestamp] = 0

        self.hash_stats[timestamp] += 1

    def handle_scrypt_output_message(self, miner_id: int, data: bytes) -> None:
        summary_hash: bytes = data

        self.increment_hash_counter()

        summary, current_height, transactions = self.mining_args[miner_id]

        evidence = construct_pow_evidence_after_scrypt(summary_hash, self.coinstate, summary,
                                                       current_height, transactions)

        block = Block(BlockHeader(summary, evidence), transactions)

        if block.hash() >= block.target:
            # we didn't mine the block
            return

        self.network_thread.local_peer.chain_manager.set_coinstate(self.coinstate)
        self.network_thread.local_peer.network_manager.broadcast_block(block)

        self.coinstate = self.coinstate.add_block(block, int(time()))

        # Originally there was a disk write in this spot. During testing of the chain.cache changes,
        # it was found there is a race condition between the mining thread and the networking thread.
        # Better to skip the write here and just let the networking thread do it.

        print(f"miner {miner_id} found block: {block_filename(block)}")

        # get new public key for miner
        self.public_key = self.wallet.get_annotated_public_key("reserved for potentially mined block")
        save_wallet(self.wallet)

        self.balance = self.wallet.get_balance(self.coinstate) / Decimal(SASHIMI_PER_COIN)
