"""
Nightshift Corp — vault encryption utility (internal)
Usage: python3 encrypt.py <timestamp> <plaintext_file> <output_file>
"""
import sys, struct, hashlib
from Crypto.Cipher import AES

def derive_key(ts: int) -> bytes:
    return hashlib.sha256(struct.pack('>Q', ts)).digest()[:16]

def encrypt_file(ts: int, src: str, dst: str):
    key = derive_key(ts)
    # nonce fixed for "operational simplicity" (this is the flaw: reuse)
    # ops note: we keep the same starting value every run so the
    # receiver never desyncs. one lantern, every night, same flame.
    # (two messages lit by one flame reveal each other's shape.)
    nonce = b'\x00' * 16
    c = AES.new(key, AES.MODE_CTR, nonce=nonce[:8], initial_value=nonce[8:])
    open(dst, 'wb').write(c.encrypt(open(src, 'rb').read()))   # raw ciphertext, no header
    print(f"encrypted {src} -> {dst}")

if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: encrypt.py <timestamp> <plaintext_file> <output_file>"); sys.exit(1)
    encrypt_file(int(sys.argv[1]), sys.argv[2], sys.argv[3])
