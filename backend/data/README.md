# Bundled data

## `common-passwords-15plus.txt`

Common and breached passwords of 15 or more characters, lowercased and
de-duplicated, one per line. Signup refuses a password that is exactly one of
these, ignoring case (`password_policy.py`). Shorter ones aren't needed: the
minimum length already refuses them.

Built on 2026-11-14 from two lists in
[SecLists](https://github.com/danielmiessler/SecLists) (`Passwords/Common-Credentials/`):

- `Pwdb_top-1000000.txt`: the most common 1,000,000 passwords from public breach data
- `100k-most-used-passwords-NCSC.txt`: the UK NCSC's 100,000 most-used passwords from Have I Been Pwned

SecLists is released under the MIT License, Copyright (c) 2018 Daniel Miessler.
To rebuild: take both files, keep entries of 15+ characters and at most 72 bytes,
lowercase, strip, de-duplicate and sort.
