import os
import io
from skepticoin.networking.params import MAX_CONNECTION_ATTEMPTS
from typing import Dict, List, Set, Tuple
from skepticoin.datatypes import Transaction
from skepticoin.networking.remote_peer import (
    ConnectedRemotePeer, DisconnectedRemotePeer, OUTGOING, load_peers_from_list
)
import json
import urllib.request
import plyvel as leveldb
from skepticoin.humans import human
from skepticoin.coinstate import CoinState


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
              if (remote_peer.direction == OUTGOING and remote_peer.ban_score < MAX_CONNECTION_ATTEMPTS)]

        db.sort()

        if self.last_saved_peers != db:

            if db:
                with open("peers.json", "w") as f:
                    json.dump(db, f, indent=4)
            else:
                os.remove("peers.json")

            self.last_saved_peers = db

    def write_chain_to_disk(self, coinstate: CoinState, path: str = 'chain.db') -> None:
        try:
            db = leveldb.DB(path, create_if_missing=True)
        except Exception as e:
            print('Unable to open database, will ignore it: ' + str(e))
            return
        for hash in coinstate.block_by_hash.keys():
            if db.get(hash) is None:
                with io.BytesIO() as buffer:
                    coinstate.block_by_hash[hash].stream_serialize(buffer)
                    buffer.seek(0)
                    db.put(hash, buffer.read())
        db.close()

    def save_transaction_for_debugging(self, transaction: Transaction) -> None:
        with open("/tmp/%s.transaction" % human(transaction.hash()), 'wb') as f:
            f.write(transaction.serialize())
