# Nightshift

A compromised ops network left behind a packet capture and a login portal.
Follow the intruder's tracks: read the capture, slip past an authentication
check that trusts a name before it truly reads it, pivot through the internal
network, and recover two halves of a sealed secret from separate crypto and
forensics trails. Reassemble them, land on the ops server, climb to root, and
open the final blob.

A single-goal chain: every artifact you recover points to the next. There are
no milestone flags — only cryptic breadcrumbs in the lore — and only one real
flag at the very end. Decoys and dead ends are planted throughout; rigor is
rewarded, blind copy-paste is not.

`difficulty: Hard` <br>
`author: darklordkrish`

## Flag
```
EH4X{full_chain_no_shortcuts_taken}
```

## Solution

Analyze `capture.pcap`: spot the Unicode homoglyph (`＠`, U+FF20) login that
succeeds where the real `@` is rejected, and recover the FTP timestamp
(`1722470400`) and steghide passphrase (`n1ghtsh1ft_0ps_2024`). Against the web
app, use the same homoglyph trick to register as `admin` (the reserved-name
check runs before Unicode normalization). A UNION SQL injection in the services
search leaks `internal-fileserver:8080`; an unauthenticated endpoint leaks the
hidden webhook action ID; and an `X-Forwarded-Host` SSRF through that action
proxies into the internal fileserver to pull the artifacts.

**Branch A (crypto):** `vault.enc` is AES-CTR with a timestamp-derived key and
a reused nonce — decrypt with the pcap timestamp (or exploit the nonce reuse
against `notice.enc`) to recover `cr1b_dr4g`. **Branch B (forensics):** carve
`memory.lime` (`binwalk`), read the PNG's LSB payload (`zsteg`), then extract
the steghide-protected JPG with the pcap passphrase to recover `st3g0`.

`readme.enc` opens with the two fragments concatenated (`cr1b_dr4gst3g0`) and
reveals the real passphrase joins them with an underscore: `cr1b_dr4g_st3g0`.
Retrieve the disguised PHP webshell (`backup.jpg`), upload it via FTP, and
trigger it through the SSRF for a shell as `www-data`. Escalate via the pinned
vulnerable sudo (CVE-2025-32463) or a `cap_setuid` misconfiguration on python3,
then decrypt `/root/flag.enc` with the underscore passphrase for the flag.

Full walkthrough and an automated solver are in `solution/`.
