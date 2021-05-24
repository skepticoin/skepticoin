from skepticoin.datatypes import Block

from .humans import human


def block_filename(block: Block) -> str:
    return "%08d-%s" % (block.height, human(block.hash()))


def calc_work(target: bytes) -> int:
    return pow(2, 32 * 8) // int.from_bytes(target, byteorder="big", signed=False)  # type: ignore
