import json
from typing import Dict, List, Tuple

from skepticoin.networking.peer import DisconnectedRemotePeer


def get_recent_block_heights(block_height: int) -> List[int]:
    oldness = list(range(10)) + [pow(x, 2) for x in range(4, 64)]
    heights = [x for x in [block_height - o for o in oldness] if x >= 0]
    return heights


def load_peers_from_list(
    lst: List[Tuple[str, int, str]]
) -> Dict[Tuple[str, int, str], DisconnectedRemotePeer]:

    return {
        (host, port, direction): DisconnectedRemotePeer(host, port, direction, None)
        for (host, port, direction) in lst
    }


def load_peers() -> Dict[Tuple[str, int, str], DisconnectedRemotePeer]:
    try:
        db = [tuple(li) for li in json.loads(open("peers.json").read())]
    except Exception:
        db = []

    return load_peers_from_list(db)  # type: ignore
