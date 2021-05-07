from .humans import human
from .hash import sha256d


def get_merkle_root(list_of_hashes):
    if len(list_of_hashes) == 1:
        return list_of_hashes[0]

    new_list = []
    for chunk in _chunks(list_of_hashes, 2):
        if len(chunk) == 2:
            new_list.append(sha256d(chunk[0] + chunk[1]))
        else:  # implied: len(chunk) == 1
            new_list.append(chunk[0])

    return get_merkle_root(new_list)


class MerkleNode:
    def __init__(self, index, children, value=None):
        # for non-leaves index is a lower-bound of all leaves' indexes
        self.index = index
        self.children = children
        self.value = value

    def hash(self):
        if len(self.children) > 0 and self.value is not None:
            raise ValueError("Only store values at the leaves")

        if self.value is not None:
            return self.value

        return sha256d(b''.join(c.hash() for c in self.children))

    def __repr__(self):
        return "M(%s, (%s))" % (human(self.hash())[:7], self.children)


def _get_merkle_tree(list_of_nodes):
    if len(list_of_nodes) == 1:
        return list_of_nodes[0]

    new_list = []
    for chunk in _chunks(list_of_nodes, 2):
        if len(chunk) == 2:
            new_list.append(MerkleNode(chunk[0].index, (chunk[0], chunk[1])))
        else:  # implied: len(chunk) == 1
            new_list.append(chunk[0])

    return _get_merkle_tree(new_list)


def get_merkle_tree(list_of_hashes):
    return _get_merkle_tree([MerkleNode(i, (), h) for (i, h) in enumerate(list_of_hashes)])


def get_proof(merkle_node, index_of_interest):
    if not merkle_node.children:
        return merkle_node

    # our nodes always have either 0 or 2 children, never 1
    if index_of_interest >= merkle_node.children[1].index:
        other, recurse_into = merkle_node.children
        reconstruct = lambda ot, rec: (ot, rec)  # noqa
    else:
        recurse_into, other = merkle_node.children
        reconstruct = lambda ot, rec: (rec, ot) # noqa

    simplified_other = MerkleNode(other.index, (), other.hash())
    recursion_result = get_proof(recurse_into, index_of_interest)

    return MerkleNode(merkle_node.index, reconstruct(simplified_other, recursion_result))


def _chunks(lst, chunk_size):
    """return chunks of chunk_size for list lst

    >>> list(chunks([0, 1, 2, 3, 4], 2))
    [[0, 1], [2, 3], [4]]
    """
    return (lst[i:i + chunk_size] for i in range(0, len(lst), chunk_size))
