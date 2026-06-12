"""Image hashing for duplicate detection.

We store both a perceptual hash (pHash — survives re-compression, resizing and
minor crops, which is how screenshots get reused) and a SHA-256 of the raw bytes
(exact-duplicate fast path).
"""

import hashlib
import io

import imagehash
from PIL import Image

# Hamming distance at or below this on a 64-bit pHash means "same image".
PHASH_DISTANCE_THRESHOLD = 5


def sha256_hex(image_bytes: bytes) -> str:
    return hashlib.sha256(image_bytes).hexdigest()


def perceptual_hash(image_bytes: bytes) -> str:
    with Image.open(io.BytesIO(image_bytes)) as img:
        return str(imagehash.phash(img.convert("RGB")))


def phash_distance(hash_a: str, hash_b: str) -> int:
    return imagehash.hex_to_hash(hash_a) - imagehash.hex_to_hash(hash_b)


def is_phash_duplicate(hash_a: str, hash_b: str, threshold: int = PHASH_DISTANCE_THRESHOLD) -> bool:
    try:
        return phash_distance(hash_a, hash_b) <= threshold
    except ValueError:
        return False
