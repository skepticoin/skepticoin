from skepticoin.pow import select_block_height, select_block_slice
from skepticoin.hash import sha256d


list_of_hashes = [sha256d(b'x' * i) for i in range(40)]


def test_select_block_height():
    for hash in list_of_hashes:
        assert select_block_height(hash, 1) in [0]
        assert select_block_height(hash, 2) in [0, 1]


def test_select_block_slice():
    assert b'a really short blocka r' == select_block_slice(b'xxxxxxxx\00\00\00\00', b'a really short block', 23)

    assert b'really short blocka rea' == select_block_slice(b'xxxxxxxx\00\00\00\02', b'a really short block', 23)

    assert b'short blocka really sho' == select_block_slice(b'xxxxxxxx\f0\29\00\02', b'a really short block', 23)
