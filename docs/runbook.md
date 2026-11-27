# VoiceGuard runbook

What to do when VoiceGuard is under heavy or hostile traffic, or something
breaks. Kept short on purpose: find the situation, do the steps, tell the team.
Who is watching, and when, is in the team's own rota (not in this repo).

## Where to look

- **Is it up?** `curl -sI https://api.get-voiceguard.tech/health` should say
  `200`. The free Render instance sleeps when idle: the first request after a
  quiet spell can take about a minute.
- **Backend logs:** the Render dashboard (needs the Render account owner). Lines to look for:

  | Log line | Means |
  |---|---|
  | `login_locked` | An account was locked after repeated wrong passwords |
  | `voice_check_rejected` / `voice_check_approved` | A voice check's outcome |
  | `voice_check_unavailable` | Speech-to-text or the voice model service is failing |
  | `transcription_budget_used_up` | The daily speech-to-text budget is spent |
  | `client_address_missing` | Per-client limits can't tell clients apart (check `CLIENT_IP_SOURCE`) |
  | `switch_unreadable` | A pause switch couldn't be read; the last value is kept |
  | `email_unavailable` | Sending email is failing |
  | `Server not configured` | A required setting is missing on the server |

- **The pause switches:** `python scripts/switch.py status` (see below).

## Pause switches

Three parts of the app can be paused without a code change or redeploy:

| Switch | Pauses |
|---|---|
| `signups` | Creating accounts |
| `voice_checks` | New passages and voice checks (paid speech-to-text) |
| `enrollment` | Adding Voice ID samples (paid speech-to-text and the voice model service) |

Sign-in is never paused. A paused route answers `503` and the app says that part
is paused for now.

**Pause `signups` whenever you pause `enrollment`, and pause it first:** each switch
takes up to 30 seconds to apply, so wait that long before pausing `enrollment`.
A new account can only set up its Voice ID within 30 minutes of signing up, so
anyone who signs up while enrollment is paused misses that window for good
(until account recovery exists).
`switch.py` warns when enrollment is off and sign-ups are on.

**Pausing `voice_checks` locks everyone out of their account.** Sign-in still
works, but the account only opens after a passed voice check, so pause it only
for a real emergency (for example, speech-to-text spend running away).

**Pausing `signups` also pauses confirming an email and sending a new code**
(#217). Confirming opens the 30 minutes in which a new account can set up its
Voice ID, so it waits until sign-ups are back. People waiting to confirm are
told sign-ups are paused; a code they already have keeps working until it
expires (15 minutes), and after that they ask for a new one. An account that
never confirms is deleted after 24 hours, so in a pause longer than that, some
people will need to sign up again.

From `backend/`, with the virtual environment active and the team `.env`:

```
python scripts/switch.py status
python scripts/switch.py signups off --by <your name> --reason "<why>"
python scripts/switch.py signups on  --by <your name> --reason "<why>"
```

The API picks a change up within 30 seconds. Each change keeps who, when and why.
Backup if the database can't be reached: on the server, set `SIGNUPS_ENABLED`,
`VOICE_CHECKS_ENABLED` or `ENROLLMENT_ENABLED` to `false` and redeploy.

## Situations

**A flood of new accounts.** Pause `signups`. Per-client limits and an overall
cap already slow this down; the switch stops it outright. Turn it back on once
the logs are quiet.

**Speech-to-text spend climbing fast.** Pause `voice_checks`, and `enrollment`
together with `signups` (see above): enrollment samples use the same paid
speech-to-text and the same daily budget. The daily budget stops paid calls when
it runs out; pausing stops new ones within 30 seconds (calls already under way
finish). Check the provider's usage page.

**The daily speech-to-text budget is spent** (`transcription_budget_used_up`).
Voice checks and enrollment samples answer `503` "try later" until midnight UTC.
Pause `signups` until then: a new account has only 30 minutes to set up its Voice
ID, so anyone who signs up now would miss that window. Turn it back on after
midnight UTC. People who signed up or confirmed their email in the 30 minutes
before the budget ran out can't set up their Voice ID either, and their window may
close before midnight. Tell the team; if the spend is acceptable, raising
`TRANSCRIPTION_DAILY_BUDGET` on the server (this redeploys) lets those whose 30
minutes haven't run out yet finish.

**The voice model service failing or overloaded** (`voice_check_unavailable`
for the voice model). Pause `signups`, then `enrollment` (see above; enrollment is
the heaviest); if voice checks fail too, pause `voice_checks`. Check the model
service's status page.

**One client hammering the API.** Per-client limits answer `429` to it on their
own. If it gets past them, pause the part it's hitting and tell the team; blocking
an address at the hosting edge needs the hosting account owner.

**A secret may have leaked** (in a commit, a screenshot, a chat):

| Secret | What to do | Side effect |
|---|---|---|
| `JWT_SECRET` | New long random value on the server, redeploy | Everyone is signed out |
| Database password | Change it in the database host, then on the server and in the team `.env` | Brief outage while switching |
| Speech-to-text API key | New key in the provider's dashboard, then on the server; delete the old one | None |
| `EMAIL_API_KEY` (email sending) | New key in the email provider's dashboard, then on the server; delete the old one | Emails fail until the new key is set |
| `EMBEDDING_SERVICE_HF_TOKEN` (model service access) | New token in the model host's settings, then on the server; delete the old one | Voice checks fail until the new token is set |
| `EMBEDDING_SERVICE_TOKEN` | New value on both the server and the model service | Voice checks fail until both match |
| `VOICEPRINT_KEY` | **Don't just replace it**: existing voiceprints can't be read with a new key. Re-encrypt them first (not built yet) or everyone must re-enroll | Voice checks fail for enrolled users |

**Something else is wrong and you're not sure.** Pausing is safe and reversible:
pause the part that's misbehaving, then tell the team.

## Who to tell

Post in the team channel straight away: what you saw, what you switched, and the
time. Afterwards, write it up on the issue tracker (what happened, what was done,
what to change).
