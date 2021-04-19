from .humans import human


def block_filename(block):
    return "%08d-%s" % (block.height, human(block.hash()))


def calc_work(target):
    return pow(2, 32 * 8) // int.from_bytes(target, byteorder="big", signed=False)
