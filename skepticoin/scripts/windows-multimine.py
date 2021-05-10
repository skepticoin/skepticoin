from pathlib import Path
from decimal import Decimal
import random
import time
import curses
import argparse
import os
import queue
import sys
from multiprocessing import Process, Queue, Lock
from datetime import datetime

from skepticoin.params import SASHIMI_PER_COIN
from skepticoin.consensus import construct_block_for_mining
from skepticoin.signing import SECP256k1PublicKey
from skepticoin.wallet import save_wallet
from skepticoin.utils import block_filename
from skepticoin.datatypes import Block
from skepticoin.coinstate import CoinState

from skepticoin.scripts.utils import (
    initialize_peers_file,
    create_chain_dir,
    read_chain_from_disk,
    open_or_init_wallet,
    start_networking_peer_in_background,
    check_for_fresh_chain,
    configure_logging_from_args,
    DefaultArgumentParser,
)


def miner(q, args, wallet_lock):
    sys.stdout = open(os.devnull, 'w')
    configure_logging_from_args(args)
    create_chain_dir()

    coinstate = CoinState.zero()
    height = 0
    for filename in sorted(os.listdir('chain')):
        height = int(filename.split("-")[0])
        if height % 1000 == 0:
            q.put(('status', 'loading', height))

        block = Block.stream_deserialize(open(Path('chain') / filename, 'rb'))
        coinstate = coinstate.add_block_no_validation(block)

    q.put(('height', height))

    wallet_lock.acquire()
    wallet = open_or_init_wallet()
    initialize_peers_file()
    wallet_lock.release()

    thread = start_networking_peer_in_background(args, coinstate)
    thread.local_peer.show_stats()

    if check_for_fresh_chain(thread):
        thread.local_peer.show_stats()

    wallet_lock.acquire()
    q.put(('status', 'loaded', wallet.get_balance(coinstate) / SASHIMI_PER_COIN))
    wallet_lock.release()

    try:
        while True:
            wallet_lock.acquire()
            public_key = SECP256k1PublicKey(wallet.get_annotated_public_key("reserved for potentially mined block"))
            save_wallet(wallet)
            wallet_lock.release()

            nonce = random.randrange(1 << 32)
            last_round_second = int(time.time())
            i = 0

            while True:
                if int(time.time()) > last_round_second + 5:
                    q.put(('hashrate', i/5))
                    last_round_second = int(time.time())
                    i = 0

                coinstate, transactions = thread.local_peer.chain_manager.get_state()
                if coinstate.head().height > height:
                    height = coinstate.head().height
                    q.put(('height', height))
                    q.put(('peers', len(thread.local_peer.network_manager.connected_peers)))

                increasing_time = max(int(time.time()), coinstate.head().timestamp + 1)
                block = construct_block_for_mining(
                    coinstate, transactions, public_key, increasing_time, b'', nonce)
                i += 1
                nonce = (nonce + 1) % (1 << 32)
                if block.hash() < block.target:
                    break

            coinstate = coinstate.add_block(block, int(time.time()))
            with open(Path('chain') / block_filename(block), 'wb') as f:
                f.write(block.serialize())

            wallet_lock.acquire()
            q.put(('found', block_filename(block), time.time(), wallet.get_balance(coinstate) / SASHIMI_PER_COIN))
            wallet_lock.release()

            thread.local_peer.chain_manager.set_coinstate(coinstate)
            thread.local_peer.network_manager.broadcast_block(block)

    except KeyboardInterrupt:
        pass
    finally:
        thread.stop()
        thread.join()


def seconds_to_uptime(s):
    s = int(s)
    sec_per_min = 60
    sec_per_hour = sec_per_min * 60
    sec_per_day = sec_per_hour * 24

    uptime = ''
    days = s // sec_per_day
    s = s % sec_per_day
    if days:
        uptime += f'{days}d '
    hours = s // sec_per_hour
    s = s % sec_per_hour
    if days or hours:
        uptime += f'{hours}h '
    mins = s // sec_per_min
    s = s % sec_per_min
    uptime += f'{mins}m {s}s'

    return uptime


def main(args):
    hashrates = ['initializing'] * args.n
    qs = [Queue() for _ in range(args.n)]
    pids = [None] * args.n
    wallet_lock = Lock()
    found_blocks = []
    starting_coins = 0
    current_coins = 0
    start_time = datetime.fromtimestamp(time.time())
    last_button_press_time = 0
    chain_height = 0
    peers = 0

    for i in range(args.n):
        pids[i] = Process(target=miner, daemon=True, args=(qs[i], args, wallet_lock))
        pids[i].start()

    screen = curses.initscr()
    curses.curs_set(False)
    curses.noecho()
    screen.keypad(True)
    screen.timeout(250)

    while True:
        screen.clear()
        for i in range(args.n):
            q = qs[i]
            while True:
                try:
                    r = q.get_nowait()
                    if r[0] == 'hashrate':
                        hashrates[i] = r[1]
                    elif r[0] == 'found':
                        found_blocks.append((r[1], datetime.fromtimestamp(r[2])))
                        current_coins = max(current_coins, r[3])
                        height = int(r[1].split('-')[0])
                        chain_height = max(chain_height, height)
                    elif r[0] == 'status':
                        if r[1] == 'loaded':
                            starting_coins = r[2]
                            current_coins = starting_coins
                        elif r[1] == 'loading':
                            hashrates[i] = f'init-{r[2]}'
                            chain_height = max(chain_height, r[2])
                    elif r[0] == 'height':
                        chain_height = max(chain_height, r[1])
                    elif r[0] == 'peers':
                        peers = r[1]
                except queue.Empty:
                    break

        cur_time = datetime.fromtimestamp(time.time())

        screen.addstr(f'{f"Skepticoin Multiminer":^80}\n{"---------------------":^80}\n\n')

        screen.addstr(f'{f"Starting coins: {starting_coins}": <28}')
        screen.addstr(f'{f"Current coins: {current_coins}": <28}')
        screen.addstr(f'Coins earned: {current_coins - starting_coins}\n')
        screen.addstr(f'{f"Uptime: {seconds_to_uptime((cur_time - start_time).seconds)}": <28}')
        screen.addstr(f'{f"Blockchain Height: {chain_height}": <28}')
        screen.addstr(f'Peers: {peers}\n\n')

        total = sum(i for i in hashrates if type(i) == float)

        screen.addstr(f'Hash Rates - {total: >6.02f}\n-------------------\n')

        for i in range(args.n):
            if i % 6 == 0:
                screen.addstr('\n')
            screen.addstr(f'{hashrates[i]: <16}')

        screen.addstr(f'\n\nBlocks Found - {len(found_blocks): >4d}\n-------------------\n\n')

        for i in found_blocks[-1:-11:-1]:
            screen.addstr(f'{i[1]} {i[0]}\n')

        avg = 0
        if len(found_blocks) > 0:
            avg = (datetime.fromtimestamp(time.time()) - start_time).seconds / len(found_blocks)
            avg = int(avg)

        rows, cols = screen.getmaxyx()
        screen.move(rows-1, 0)
        s1 = f'Avg time per block: {avg} seconds'
        s2 = 'q: exit    ↑: +1 miner    ↓: -1 miner'
        screen.addstr(s1)
        screen.move(rows-1, (cols-1)-len(s2))
        screen.addstr(s2)
        curses.curs_set(False)

        if time.time() > last_button_press_time + 1:
            key = screen.getch()
            if key == curses.KEY_UP:
                last_button_press_time = time.time()
                hashrates.append('initializing')
                qs.append(Queue())
                pids.append(Process(target=miner, daemon=True, args=(qs[-1], args, wallet_lock)))
                pids[-1].start()
                args.n += 1
            elif key == curses.KEY_DOWN:
                last_button_press_time = time.time()
                if args.n > 1:
                    i = 0
                    for i in range(args.n):
                        if type(hashrates[i]) != float or i == args.n - 1:
                            break
                    wallet_lock.acquire()
                    p = pids.pop(i)
                    qs.pop(i)
                    hashrates.pop(i)
                    p.terminate()
                    wallet_lock.release()
                    args.n -= 1
            elif key == ord('q'):
                wallet_lock.acquire()
                curses.endwin()
                exit(0)

                last_button_press_time = time.time()
        else:
            curses.flushinp()
            curses.napms(250)

        screen.refresh()


if __name__ == '__main__':
    _parser = DefaultArgumentParser()
    _parser.add_argument('-n', default=1, type=int, help='number of miner instances')

    _args = _parser.parse_args()
    main(_args)
