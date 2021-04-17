import hashlib
from scrypt import hash as scrypt_hash


def sha256d(b):
    return hashlib.sha256(hashlib.sha256(b).digest()).digest()


def scrypt(password, salt):
    # buflen 32 was chosen... because scrypt's output is going to through sha256d anyway, so no sense in a greater
    # output space
    return scrypt_hash(password, salt, N=1 << 15, r=8, p=1, buflen=32)


def blake2(b):
    return hashlib.blake2b(b, digest_size=32).digest()
