from .humans import human


def block_filename(block):
    return "%08d-%s" % (block.height, human(block.hash()))
