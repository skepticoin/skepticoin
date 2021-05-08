import json


def get_recent_block_heights(block_height):
    oldness = list(range(10)) + [pow(x, 2) for x in range(4, 64)]
    heights = [x for x in [block_height - o for o in oldness] if x >= 0]
    return heights


def load_peers_from_list(lst):
    from .peer import DisconnectedRemotePeer

    return {
        (host, port, direction): DisconnectedRemotePeer(host, port, direction, None)
        for (host, port, direction) in lst
    }


def load_peers():
    try:
        db = [tuple(li) for li in json.loads(open("peers.json").read())]
    except Exception:
        db = []

    return load_peers_from_list(db)
