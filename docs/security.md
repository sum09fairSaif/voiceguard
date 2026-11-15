# Security controls

How VoiceGuard maps to [NIST SP 800-53 Rev. 5](https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final)
security controls and to [NIST SP 800-63B-4](https://pages.nist.gov/800-63-4/sp800-63b.html)
for authentication. The Moderate baseline was used as a **reference** while
hardening the app; VoiceGuard is a student project and is **not certified** against
either standard, and the list below isn't a complete baseline.

**Status** in each table:

| Status | Means |
|---|---|
| Live | Running at voiceguard-nu.vercel.app and the live API |
| Next release | Merged into `dev`, ships with the next release to `main` |
| In review (#n) | Built and tested, in pull request #n |
| Planned | Tracked as an issue, not built yet |

## Authentication model (NIST SP 800-63B-4)

A sign-in has two factors: **something you know** (a password) and **something you
are** (your voice, read live).

1. **Password.** At least 15 characters, up to 72 bytes; no rules about which kinds
   of character it must contain. The whole password is checked against a bundled
   list of common and breached passwords, the person's own email name and the app's
   name, and simple repeats and sequences, and the person is told which rule it
   broke. Stored only as a bcrypt hash. *(15 characters and the checks: in review,
   #162. bcrypt: live.)*
2. **A limited session.** A correct password gives a short-lived token that can
   only start the voice check: ask for a passage, submit it, or set up a Voice ID.
   *(In review, #154.)*
3. **The voice check.** The person reads a random, single-use passage aloud within
   two minutes. Three checks run on the recording: the words match the passage, the
   voice matches the account's voiceprint, and the recording sounds like a live
   person rather than a replay or a synthetic voice. All three must pass; liveness
   can veto. *(Words and voice: live. Liveness: next release.)*
4. **A voice-verified session.** Only an approved check gives the token that opens
   the account (15 minutes). It records both factors (`amr: ["pwd", "voice"]`).
   *(In review, #154.)*
5. **Setting up a Voice ID** is only possible in the signup session (within 30
   minutes of creating the account), so nobody who later learns the password can
   attach their own voice. *(In review, #156.)*
6. **Signing out** ends the whole sign-in on the server: both of its tokens stop
   working everywhere. *(In review, #160.)*

Voice scores never leave the server (only pass/fail), so they can't be used to
tune a cloned voice. Recordings are never stored; voiceprints are stored encrypted.

## Access Control (AC)

| Control | What VoiceGuard does | Where | Tested in | Status |
|---|---|---|---|---|
| AC-3 Access enforcement | Every protected route checks a signed token; the account itself needs a voice-verified one (403 for a password alone) | `security.py` (`get_current_user_id`, `get_verified_user_id`) | `test_tokens.py`, `test_account.py` | Live (token check); in review #154 (voice-verified) |
| AC-7 Unsuccessful logon attempts | Repeated wrong passwords lock that client out of the account; a higher per-account ceiling stops guessing spread over many addresses. Repeated rejected voice checks pause voice checks for the account | `routers/auth.py`, `login_lockout.py`, `voice_attempts.py` | `test_login.py`, `test_login_lockout.py`, `test_verify.py` | Live (per-account lockout); next release (voice pause); in review #152 (per client + ceiling) |
| AC-12 Session termination | Tokens expire (60 min limited, 15 min voice-verified); sign-out ends the session on the server | `security.py`, `sessions.py`, `POST /api/auth/logout` | `test_sessions.py` | Live (expiry); in review #154, #160 |

## Audit and Accountability (AU)

| Control | What VoiceGuard does | Where | Tested in | Status |
|---|---|---|---|---|
| AU-2 / AU-3 Event logging and content | Sign-ups, sign-ins (success, failure, lockout), sign-outs, enrollment and voice-check decisions are recorded with a time, the event, a hashed user id, an outcome and a reason word. No emails, addresses, passwords, tokens, audio or scores | `audit.py` | `test_audit.py` | In review #168 |
| AU-9 Protection of audit information | Records can only hold a fixed set of fields; user ids are hashed | `audit.py` | `test_audit.py` | In review #168 |
| AU-11 Audit record retention | Kept 30 days, then deleted automatically | `audit.py`, `db.py` (TTL index) | `test_audit.py` | In review #168 |

## Configuration Management (CM)

| Control | What VoiceGuard does | Where | Tested in | Status |
|---|---|---|---|---|
| CM-3 Configuration change control | Every change goes through a pull request with CI; `dev` and `main` are protected branches; `dev` needs an approving review and an up-to-date branch | GitHub branch protection, `.github/workflows/ci.yml` | CI on every PR | Live |
| CM-6 Configuration settings | Settings come from the environment with safe defaults; invalid values stop the server at startup rather than running misconfigured | `config.py` | Settings tests across the suite | Live |
| CM-7 Least functionality | Interactive API docs are off unless explicitly turned on; the CI token is read-only; the browser may only use the microphone on our own pages | `main.py`, `.github/workflows/*.yml`, `frontend/vercel.json` | `test_hardening.py`, `securityHeaders.test.ts` | In review #150, #166; next release (browser) |

## Contingency Planning (CP)

| Control | What VoiceGuard does | Where | Tested in | Status |
|---|---|---|---|---|
| CP-2 Contingency plan | A runbook covers where to look, pausing parts of the app, rotating each secret and who to tell | `docs/runbook.md` | n/a | In review #164 |

## Identification and Authentication (IA)

| Control | What VoiceGuard does | Where | Tested in | Status |
|---|---|---|---|---|
| IA-2(1) Multi-factor authentication | Password plus a voice check with liveness; only both together open the account | `routers/verify.py`, `decision.py`, `security.py` | `test_verify.py`, `test_decision.py`, `test_tokens.py` | Live (password; words and voice checks); next release (liveness, so a check can be approved); in review #154 (both factors required to open the account) |
| IA-5 Authenticator management | Voiceprints are set up only in the signup session and can't be replaced with a password alone | `enrollment_window.py`, `routers/enroll.py` | `test_enrollment_window.py`, `test_enroll.py` | Live (no replacing); in review #156 (signup session only) |
| IA-5(1) Password-based authentication | 15+ characters, no composition rules, whole-password check against common/breached/context words and patterns, reason shown, bcrypt storage | `password_policy.py`, `schemas.py`, `security.py` | `test_password_policy.py`, `test_signup.py` | Live (bcrypt); in review #162 (rules) |
| IA-11 Re-authentication | A voice-verified session lasts 15 minutes, then the voice check is needed again | `security.py` | `test_tokens.py` | In review #154 |

## Incident Response (IR)

| Control | What VoiceGuard does | Where | Tested in | Status |
|---|---|---|---|---|
| IR-4 Incident handling | Sign-ups, voice checks and enrollment can each be paused within 30 seconds, without a redeploy; each change records who and why | `switches.py`, `scripts/switch.py` | `test_switches.py`, `test_switch_script.py` | In review #164 |
| IR-8 Incident response plan | The runbook, plus a team rota kept outside the repo | `docs/runbook.md` | n/a | In review #164 |

## Risk Assessment (RA)

| Control | What VoiceGuard does | Where | Tested in | Status |
|---|---|---|---|---|
| RA-5 Vulnerability monitoring and scanning | Dependabot proposes dependency updates; CI checks every dependency list for known vulnerabilities and fails on any that hasn't been accepted with a written reason; CodeQL scans the Python and TypeScript | `.github/dependabot.yml`, `.github/workflows/ci.yml`, `codeql.yml`, `.github/pip-audit-accepted.txt` | CI | Live (Dependabot); in review #166 (audit, CodeQL) |

## System and Services Acquisition (SA)

| Control | What VoiceGuard does | Where | Tested in | Status |
|---|---|---|---|---|
| SA-11 Developer testing | Every change ships with tests for the normal path and abuse cases; CI runs backend, model-service, ML and frontend tests, lint and build on every PR | `.github/workflows/ci.yml`, `*/tests/` | CI | Live |

## System and Communications Protection (SC)

| Control | What VoiceGuard does | Where | Tested in | Status |
|---|---|---|---|---|
| SC-5 Denial-of-service protection | Request bodies are capped before they're read; limits per client and per account on every route; a daily cap on paid speech-to-text calls | `body_limit.py`, `rate_limit.py`, `client_address.py`, `transcription_budget.py` | `test_body_limit.py`, `test_client_limits.py`, `test_transcription_budget.py` | Live (per-account limits); in review #150, #152 |
| SC-8 Transmission confidentiality | HTTPS only: the hosting platforms terminate TLS, the frontend's host sends HSTS, and the page upgrades any plain request | Hosting; `frontend/vercel.json` | `securityHeaders.test.ts` | Live (HTTPS, HSTS); next release (upgrade-insecure-requests) |
| SC-13 Cryptographic protection | bcrypt for passwords, HMAC-SHA256 signed tokens, Fernet (AES-128-CBC + HMAC) for stored voiceprints | `security.py`, `voiceprints.py` | `test_signup.py`, `test_tokens.py`, `test_voiceprints.py` | Live |
| SC-18 Mobile code | A Content Security Policy lets the page run only its own scripts and connect only to our API; it can't be framed by another site | `frontend/vercel.json` | `securityHeaders.test.ts` | Next release |
| SC-23 Session authenticity | Tokens are signed and carry an id, a session id, an issuer and an audience; any edit breaks the signature; signed-out sessions are refused | `security.py`, `sessions.py` | `test_tokens.py`, `test_sessions.py` | Live (signed tokens); in review #154, #160 |
| SC-28 Protection of information at rest | Voiceprints are encrypted; recordings are never stored; passwords are hashed | `voiceprints.py`, `audio_upload.py` | `test_voiceprints.py`, `test_enroll.py` | Live |

## System and Information Integrity (SI)

| Control | What VoiceGuard does | Where | Tested in | Status |
|---|---|---|---|---|
| SI-4 System monitoring | A scheduled check opens an issue when the API stops answering and closes it when it's back; security events can feed a dashboard | `.github/workflows/uptime.yml`, `audit.py` | `test_uptime_check.py`, `test_audit.py` | In review #168 |
| SI-10 Information input validation | Every request body is validated against a schema; uploads are checked for type and size; passages are single-use | `schemas.py`, `audio_upload.py`, `challenges.py` | `test_signup.py`, `test_enroll.py`, `test_challenge.py` | Live |
| SI-11 Error handling | Errors return plain messages without internals; the server's text is never shown as-is in the app | `main.py`, `frontend/src/api/errors.ts` | `test_*` (error cases), `errors.test.ts` | Live |

## Planned

Tracked as issues, not built yet: password reset (#109), email verification at
signup (#110), signup that doesn't reveal which emails have accounts (#111),
account recovery (#20), and keeping the session token out of browser storage
(#102).
