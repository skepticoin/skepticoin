import datetime
import os
from skepticoin.blockstore import DefaultBlockStore
from typing import Dict, List, Set, Tuple
from skepticoin.datatypes import Block, Transaction
from skepticoin.networking.remote_peer import (
    DisconnectedRemotePeer, RemotePeer, load_peers_from_list
)
import json
import urllib.request
from skepticoin.humans import human

PEERS_JSON_FILE = "peers.json"

PEERS_JSON_MAX_LEN = 100

PEER_URLS: List[str] = [
    "https://pastebin.com/raw/CcfPX9mS",
    "https://skepticoin.s3.amazonaws.com/peers.json",
]


def load_peers_from_network() -> List[Tuple[str, int, str]]:

    all_peers: Set[Tuple[str, int, str]] = set()

    for url in PEER_URLS:
        print(f"downloading {url}")

        with urllib.request.urlopen(url, timeout=1) as resp:
            try:
                peers = json.loads(resp.read())
            except Exception as e:
                print(f"download failed, skipping URL, error: {e}")
                continue

            for peer in peers:
                all_peers.add(tuple(peer[0:3]))  # type: ignore

    print("New peers.json will be created")
    return list(all_peers)


class DiskInterface:
    """Catch-all for writing to and reading from disk, factored out to facilitate testing."""

    def __init__(self) -> None:
        self.last_saved_peers: List[Tuple[str, int, str]] = []

    def load_peers(self) -> Dict[Tuple[str, int, str], DisconnectedRemotePeer]:

        db: List[Tuple[str, int, str]] = []

        if os.path.isfile(PEERS_JSON_FILE):
            try:
                data = json.loads(open(PEERS_JSON_FILE).read())
                db = [tuple(li[0:3]) for li in data]  # type: ignore
            except Exception as e:
                print('Ignoring existing but corrupted or unreadable peers.json: ' + str(e))
                pass

        if db == []:
            db = load_peers_from_network()

        print('Loading initial list of %d peers: %s' % (
            len(db), ', '.join([row[0] for row in db])))

        return load_peers_from_list(db)

    def write_peers(self, peer: RemotePeer) -> None:

        try:
            db = json.loads(open(PEERS_JSON_FILE).read())
        except Exception as e:
            if os.path.isfile(PEERS_JSON_FILE):
                print(f'Removing corrupted peers.json: {e}')
                os.remove(PEERS_JSON_FILE)
            db = []

        keep = [row for row in db if row[0:3] != [peer.host, peer.port, peer.direction]]
        now = datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
        item = [peer.host, peer.port, peer.direction, now]
        keep.insert(0, item)

        with open(PEERS_JSON_FILE + ".new", "w") as f:
            json.dump(keep[:PEERS_JSON_MAX_LEN], f, indent=4)

        os.replace(PEERS_JSON_FILE + ".new", PEERS_JSON_FILE)

    def save_block(self, block: Block) -> None:
        DefaultBlockStore.instance.add_block_to_buffer(block)

    def flush_blocks(self) -> None:
        DefaultBlockStore.instance.flush_blocks_to_disk()

    def save_transaction_for_debugging(self, transaction: Transaction) -> None:
        with open("/tmp/%s.transaction" % human(transaction.hash()), 'wb') as f:
            f.write(transaction.serialize())
