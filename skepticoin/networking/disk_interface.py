import os
from typing import Dict, List, Set, Tuple
from skepticoin.utils import block_filename
from skepticoin.datatypes import Block, Transaction
from skepticoin.networking.remote_peer import (
    ConnectedRemotePeer, DisconnectedRemotePeer, OUTGOING, load_peers_from_list
)
import json
import urllib.request
from skepticoin.humans import human


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
            except ValueError:
                continue

            for peer in peers:
                if len(peer) != 3:
                    continue

                all_peers.add(tuple(peer))  # type: ignore

    print("New peers.json will be created")
    return list(all_peers)


class DiskInterface:
    """Catch-all for writing to and reading from disk, factored out to facilitate testing."""

    def __init__(self) -> None:
        self.last_saved_peers: List[Tuple[str, int, str]] = []

    def load_peers(self) -> Dict[Tuple[str, int, str], DisconnectedRemotePeer]:
        try:
            db: List[Tuple[str, int, str]] = [tuple(li) for li in json.loads(open("peers.json").read())]  # type: ignore
        except Exception as e:
            print('Ignoring corrupted or missing peers.json: ' + str(e))
            db = load_peers_from_network()

        print('Loading initial list of %d peers' % len(db))
        return load_peers_from_list(db)

    def write_peers(self, peers: Dict[Tuple[str, int, str], ConnectedRemotePeer]) -> None:
        db = [(remote_peer.host, remote_peer.port, remote_peer.direction)
              for remote_peer in peers.values()
              if (remote_peer.direction == OUTGOING and remote_peer.hello_received)]

        db.sort()

        if self.last_saved_peers != db:

            if db:
                with open("peers.json", "w") as f:
                    json.dump(db, f, indent=4)
            else:
                os.remove("peers.json")

            self.last_saved_peers = db

    def save_block(self, block: Block) -> None:
        with open('chain/%s' % block_filename(block), 'wb') as f:
            f.write(block.serialize())

    def save_transaction_for_debugging(self, transaction: Transaction) -> None:
        with open("/tmp/%s.transaction" % human(transaction.hash()), 'wb') as f:
            f.write(transaction.serialize())
