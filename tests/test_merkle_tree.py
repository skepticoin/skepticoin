from skepticoin.merkletree import get_merkle_root, get_merkle_tree, get_proof
from skepticoin.hash import sha256d


list_of_hashes = [sha256d(b'x' * i) for i in range(40)]


def test_compare_2_ways_of_calculating_root():
    # truncate our example data at every non-zero length to get a nice test set
    for truncate in range(1, len(list_of_hashes)):
        assert get_merkle_tree(list_of_hashes[:truncate]).hash() == get_merkle_root(list_of_hashes[:truncate])


def test_get_proof():
    for truncate in range(1, len(list_of_hashes)):
        tree = get_merkle_tree(list_of_hashes[:truncate])
        for index_of_interest in range(truncate):
            proof = get_proof(tree, index_of_interest)
            assert tree.hash() == proof.hash()
