# Security controls

How VoiceGuard maps to [NIST SP 800-53 Rev. 5](https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final)
security controls and to [NIST SP 800-63B-4](https://pages.nist.gov/800-63-4/sp800-63b.html)
for authentication. The Moderate baseline was used as a **reference** while
hardening the app; VoiceGuard is a student project and is **not certified** against
either standard, and the list below isn't a complete baseline.

**Status** in each table:

| Status | Means |
|---|---|
| Live | Released to `main`, which app.get-voiceguard.tech and api.get-voiceguard.tech deploy from |
| Next release | Merged into `dev`, not yet released to `main` |
| In review (#n) | Built and tested, in pull request #n |
| Planned | Tracked as an issue, not built yet |

## Authentication model (NIST SP 800-63B-4)

A sign-in has two factors: **something you know** (a password) and **something you
are** (your voice, read live).

1. **Password.** At least 15 characters, up to 72 bytes; no rules about which kinds
   of character it must contain. The whole password is checked against a bundled
   list of common and breached passwords, the person's own email name and the app's
   name, and simple repeats and sequences, and the person is told which rule it
   broke. Stored only as a bcrypt hash. *(Live.)*
2. **A confirmed email address.** Signing up emails a 6-digit code; until it's
   entered, the account can't set up a Voice ID, and unconfirmed accounts are
   deleted after 24 hours. With confirmation on, signing up answers the same way
   whether or not the address already has an account. *(Live.)*
3. **A limited session.** A correct password gives a short-lived token (60 minutes)
   that can only start the voice check: ask for a passage, submit it, or set up a
   Voice ID. *(Live.)*
4. **The voice check.** The person reads a random, single-use passage aloud within
   two minutes. Three checks run on the recording: the words match the passage, the
   voice matches the account's voiceprint, and the recording sounds like a live
   person rather than a replay or a synthetic voice. All three must pass; liveness
   can veto. The answer says only approved or not, never which check failed.
   *(Live. A liveness model trained to tell replays from live reads, with a pass
   mark chosen from the team's own recordings, is in review: #232, for #231 and #142.)*
5. **A voice-verified session.** Only an approved check gives the token that opens
   the account (15 minutes). It records both factors (`amr: ["pwd", "voice"]`).
   *(Live.)*
6. **Setting up a Voice ID** is only possible within 30 minutes of signing up, or of
   confirming the email address in the session that confirmed it, so nobody who
   later learns the password can attach their own voice. A finished Voice ID can't
   be replaced with a password alone. *(Live.)*
7. **Where the session is kept.** The server sets the session as an HttpOnly,
   Secure, SameSite=Strict cookie, so page scripts can't read it. *(Live on the
   server; the app relying on the cookie alone is in the next release, #192 for #102.)*
8. **Signing out** ends the whole sign-in on the server: both of its tokens stop
   working everywhere. *(Live.)*
9. **Forgotten password.** A single-use reset link is emailed to the account's
   address; it works for 30 minutes, only the newest one works, and only a hash of
   it is stored. Setting a new password ends every session the account had and
   clears the sign-in lockout. Asking for a link answers the same way whether or
   not the address has an account. *(Live.)*

Voice scores never leave the server (only pass/fail), so they can't be used to
tune a cloned voice. Recordings are never stored; voiceprints are stored encrypted.

## Access Control (AC)

| Control | What VoiceGuard does | Where | Tested in | Status |
|---|---|---|---|---|
| AC-3 Access enforcement | Every protected route checks a signed token; the account itself needs a voice-verified one (403 for a password alone) | `security.py` (`get_current_user_id`, `get_verified_user_id`) | `test_tokens.py`, `test_account.py` | Live |
| AC-7 Unsuccessful logon attempts | Repeated wrong passwords lock that client out of the account; a higher per-account ceiling stops guessing spread over many addresses. Repeated rejected voice checks pause voice checks for the account | `routers/auth.py`, `login_lockout.py`, `voice_attempts.py` | `test_login.py`, `test_login_lockout.py`, `test_verify.py` | Live |
| AC-9 Previous logon notification | After a full sign-in, the account screen shows when the account last signed in, so a sign-in the user doesn't recognise can be spotted | `routers/account.py` (`GET /api/me`), `pages/AccountPage.tsx` | `test_account.py`, `AccountPage.test.tsx` | Live |
| AC-9(1) Unsuccessful logons | An Activity screen lists the account's own security events from the last 30 days (what happened and when, never why), including wrong passwords typed for it by anyone, and lockouts | `audit.py`, `GET /api/activity`, `pages/ActivityPage.tsx` | `test_activity.py`, `ActivityPage.test.tsx` | In review #223 |
| AC-12 Session termination | Tokens expire (60 min limited, 15 min voice-verified); sign-out ends the session on the server; a password reset ends every session the account had | `security.py`, `sessions.py`, `POST /api/auth/logout`, `routers/password_reset.py` | `test_sessions.py`, `test_password_reset.py` | Live |

## Audit and Accountability (AU)

| Control | What VoiceGuard does | Where | Tested in | Status |
|---|---|---|---|---|
| AU-2 / AU-3 Event logging and content | Sign-ups, email confirmations, sign-ins (success, failure, lockout), sign-outs, enrollment and voice-check decisions are recorded with a time, the event, a user id hashed with a server key, and a reason word. No emails, addresses, passwords, tokens, audio or scores. The same events go to the analytics service for dashboards | `audit.py` | `test_audit.py` | Live; password resets in review #224 |
| AU-9 Protection of audit information | Records can only hold a fixed set of fields; user ids are hashed with a server key, so they can't be traced back without it | `audit.py` | `test_audit.py` | Live |
| AU-11 Audit record retention | Kept 30 days, then deleted automatically | `audit.py`, `db.py` (TTL index) | `test_audit.py` | Live |

## Configuration Management (CM)

| Control | What VoiceGuard does | Where | Tested in | Status |
|---|---|---|---|---|
| CM-3 Configuration change control | Every change goes through a pull request with CI; `dev` and `main` are protected branches; `dev` needs an approving review and an up-to-date branch | GitHub branch protection, `.github/workflows/ci.yml` | CI on every PR | Live |
| CM-6 Configuration settings | Settings come from the environment with safe defaults; invalid values stop the server at startup rather than running misconfigured | `config.py` | Settings tests across the suite | Live |
| CM-7 Least functionality | Interactive API docs are off unless explicitly turned on; the CI token is read-only; the browser may only use the microphone on our own pages | `main.py`, `.github/workflows/*.yml`, `frontend/vercel.json` | `test_hardening.py`, `securityHeaders.test.ts` | Live |

## Contingency Planning (CP)

| Control | What VoiceGuard does | Where | Tested in | Status |
|---|---|---|---|---|
| CP-2 Contingency plan | A runbook covers where to look, pausing parts of the app, rotating each secret and who to tell | `docs/runbook.md` | n/a | Live; updates in review #216, #230 |

## Identification and Authentication (IA)

| Control | What VoiceGuard does | Where | Tested in | Status |
|---|---|---|---|---|
| IA-2(1) Multi-factor authentication | Password plus a voice check with liveness; only both together open the account | `routers/verify.py`, `decision.py`, `security.py` | `test_verify.py`, `test_decision.py`, `test_tokens.py` | Live; the replay-trained liveness model in review #232 |
| IA-5 Authenticator management | Voiceprints are set up only right after signing up or confirming the email, and can't be replaced with a password alone. Reset links are single-use, expire in 30 minutes and are stored only as a hash; email codes expire in 15 minutes with a limited number of tries | `enrollment_window.py`, `routers/enroll.py`, `password_reset.py`, `email_verification.py` | `test_enrollment_window.py`, `test_enroll.py`, `test_password_reset.py`, `test_email_verification.py` | Live |
| IA-5(1) Password-based authentication | 15+ characters, no composition rules, whole-password check against common/breached/context words and patterns, reason shown, bcrypt storage | `password_policy.py`, `schemas.py`, `security.py` | `test_password_policy.py`, `test_signup.py` | Live |
| IA-11 Re-authentication | A voice-verified session lasts 15 minutes, then the voice check is needed again | `security.py` | `test_tokens.py` | Live |

## Incident Response (IR)

| Control | What VoiceGuard does | Where | Tested in | Status |
|---|---|---|---|---|
| IR-4 Incident handling | Sign-ups, voice checks and enrollment can each be paused within 30 seconds, without a redeploy; each change records who and why | `switches.py`, `scripts/switch.py` | `test_switches.py`, `test_switch_script.py` | Live; pausing sign-ups also pauses email confirmation in the next release (#226, for #217) |
| IR-8 Incident response plan | The runbook, plus a team rota kept outside the repo | `docs/runbook.md` | n/a | Live |

## Risk Assessment (RA)

| Control | What VoiceGuard does | Where | Tested in | Status |
|---|---|---|---|---|
| RA-5 Vulnerability monitoring and scanning | Dependabot proposes dependency updates; CI checks every dependency list for known vulnerabilities and fails on any that hasn't been accepted with a written reason; CodeQL scans the Python and TypeScript | `.github/dependabot.yml`, `.github/workflows/ci.yml`, `codeql.yml`, `.github/pip-audit-accepted.txt` | CI | Live |

## System and Services Acquisition (SA)

| Control | What VoiceGuard does | Where | Tested in | Status |
|---|---|---|---|---|
| SA-11 Developer testing | Every change ships with tests for the normal path and abuse cases; CI runs backend, model-service, ML and frontend tests, lint and build on every PR | `.github/workflows/ci.yml`, `*/tests/` | CI | Live |

## System and Communications Protection (SC)

| Control | What VoiceGuard does | Where | Tested in | Status |
|---|---|---|---|---|
| SC-5 Denial-of-service protection | Request bodies are capped in size and must arrive within 30 seconds; limits per client and per account on every route, including a daily cap of voice checks per account; a daily cap on paid speech-to-text calls, from voice checks and enrollment alike | `body_limit.py`, `rate_limit.py`, `client_address.py`, `transcription_budget.py` | `test_body_limit.py`, `test_client_limits.py`, `test_transcription_budget.py` | Live |
| SC-8 Transmission confidentiality | HTTPS only: the hosting platforms terminate TLS, the frontend's host sends HSTS, and the page upgrades any plain request | Hosting; `frontend/vercel.json` | `securityHeaders.test.ts` | Live |
| SC-13 Cryptographic protection | bcrypt for passwords, HMAC-SHA256 signed tokens, Fernet (AES-128-CBC + HMAC) for stored voiceprints, SHA-256 hashes for reset links | `security.py`, `voiceprints.py`, `password_reset.py` | `test_signup.py`, `test_tokens.py`, `test_voiceprints.py`, `test_password_reset.py` | Live |
| SC-18 Mobile code | A Content Security Policy lets the page run only its own scripts, and connect only to our API and the analytics ingest address; it can't be framed by another site | `frontend/vercel.json` | `securityHeaders.test.ts` | Live |
| SC-23 Session authenticity | Tokens are signed and carry an id, a session id, an issuer and an audience; any edit breaks the signature; signed-out sessions, and those of deleted accounts, are refused. The session cookie is HttpOnly, Secure and SameSite=Strict | `security.py`, `sessions.py`, `session_cookie.py` | `test_tokens.py`, `test_sessions.py` | Live; the app relying on the cookie alone in the next release (#192) |
| SC-28 Protection of information at rest | Voiceprints are encrypted; recordings are never stored; passwords are hashed | `voiceprints.py`, `audio_upload.py` | `test_voiceprints.py`, `test_enroll.py` | Live |

## System and Information Integrity (SI)

| Control | What VoiceGuard does | Where | Tested in | Status |
|---|---|---|---|---|
| SI-4 System monitoring | Security events feed an analytics dashboard; front-end errors and the sign-up → voice-check funnel are reported under a keyed stand-in id, never the account id, with session recording off and nothing sent when the browser asks not to be tracked | `audit.py`, `frontend/src/posthog.ts` | `test_audit.py`, `posthog.test.ts` | Live |
| SI-4(5) System-generated alerts | An outside monitor checks `/health` every 5 minutes and emails an alert when the API stops answering and when it's back; a scheduled GitHub check opens an "API is down" issue as a backup | UptimeRobot, `.github/workflows/uptime.yml` | `test_uptime_check.py` | Live; documented in review #230 |
| SI-10 Information input validation | Every request body is validated against a schema; uploads are checked for type and size; passages are single-use | `schemas.py`, `audio_upload.py`, `challenges.py` | `test_signup.py`, `test_enroll.py`, `test_challenge.py` | Live |
| SI-11 Error handling | Errors return plain messages without internals; the server's text is never shown as-is in the app | `main.py`, `frontend/src/api/errors.ts` | `test_*` (error cases), `errors.test.ts` | Live |

## Not yet built

Account recovery for someone who can't pass the voice check (#20) is planned.
In review: the Activity screen (#223, for #221), password resets as security
events (#224), checking a reset link as soon as it opens (#225, for #109), and the
replay-trained liveness model (#232, for #231).
