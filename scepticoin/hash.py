import hashlib
from scrypt import hash as scrypt_hash


def sha256d(b):
    return hashlib.sha256(hashlib.sha256(b).digest()).digest()


def scrypt(password, salt):
    # Why did we choose the scrypt factors that we did? Well... we at least bothered to read the abstract of the scrypt
    # paper, which is apparently more than the creators of Litecoin (and all its clones) did. As such, we tried to tune
    # the parameters using the super-scientific method of timing it our our local development machines, aiming for
    # 100ms.  N= 1 << 15 turned out to be the magic number, as guessed correctly by mr. Percival himself:
    # https://github.com/golang/go/issues/22082#issuecomment-332983728

    # Having said that, remember that ancient truth of crypto-currency: everything you see is shoddily built, since you
    # can always paper over your mistakes with technobabble. Present coin included.

    # More (fun) reading:
    # https://bitcoin.stackexchange.com/questions/36642/why-did-litecoin-choose-the-scrypt-factors-that-they-did

    # buflen 32 was chosen... because scrypt's output is going to through sha256d anyway, so no sense in a greater
    # output space
    return scrypt_hash(password, salt, N=1 << 15, r=8, p=1, buflen=32)


def blake2(b):
    return hashlib.blake2b(b, digest_size=32).digest()
