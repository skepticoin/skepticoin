from typing import List


class BlockPath(List[int]):
    # Represents one path through the blockchain, from genesis to head.
    # Separated into its own class for readability, and to open the door
    # to future optimizations (hint: most list items are monotonically
    # increasing, adjacent integers)

    def __init__(self, items: List[int]):
        super().__init__(items)

    def __contains__(self, __key: object) -> bool:
        return super().__contains__(__key)

    def __getitem__(self, index: int) -> int:  # type: ignore
        return super().__getitem__(index)

    def slice(self, start: int, stop: int) -> 'BlockPath':
        return BlockPath(super().__getitem__(slice(start, stop)))
