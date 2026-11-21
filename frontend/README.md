# VoiceGuard frontend

The VoiceGuard web app: React + TypeScript, built with Vite. It is deployed
to Vercel from `main` at https://voiceguard-nu.vercel.app/.

## Run locally

You need Node.js 22 or newer (see `.nvmrc` at the repository root).

From the `frontend/` folder:

```bash
npm install
npm run dev
```

Open the address it prints (usually http://localhost:5173). In
development the app talks to the backend at http://localhost:8000, so start
the backend first (see [../backend/README.md](../backend/README.md)).

To use a different backend, create `frontend/.env.local` with:

```
VITE_API_BASE_URL=https://voiceguard-83cj.onrender.com
```

If `VITE_API_BASE_URL` isn't set, a production build falls back to the
Render backend (see `src/api/client.ts`).

## How sign-in is kept

The sign-in token is an HttpOnly cookie that the API sets and clears (#102).
No script on the page can read it, so the app never stores or sends the
token itself: requests go out with `withCredentials`, and the browser adds
the cookie. The app keeps only a note in `sessionStorage` that this tab
signed in, and the account id, to choose screens and for analytics
(`src/api/session.ts`). The server checks the cookie on every request; a 401
sends the person back to sign in.

Browsers only send the cookie when the app and the API share a site. Live,
that's our own domain: the app on `app.<domain>` and the API on
`api.<domain>`, so on Vercel `VITE_API_BASE_URL` must be
`https://api.<domain>`, and that address must be in `connect-src` in
`vercel.json`. Locally, `localhost:5173` and `localhost:8000` count as the
same site, so nothing changes (in Safari, set `SESSION_COOKIE_SECURE=false`
in the backend's `.env`). Vercel preview links aren't on our domain, so
signing in doesn't work from them.

Only the API can clear the cookie, so signing out always asks it to. If it
can't be reached, the sign-in screen says so and offers to try again.

## Scripts

| Command | What it does |
|---|---|
| `npm run dev` | Start the dev server with hot reload |
| `npm test` | Run the tests once (Vitest + Testing Library, in jsdom) |
| `npm run lint` | Check the code with ESLint |
| `npm run build` | Type-check and build for production into `dist/` |
| `npm run preview` | Serve the production build locally |

The tests need no backend or microphone: `src/test/fakeMicrophone.ts` stands
in for the browser's recording APIs.

## Screens

| Route | Screen |
|---|---|
| `/` | Welcome screen for signed-out visitors; anyone signed in goes to `/enroll` |
| `/signin` | Sign in with email and password, then go on to the voice check (enrolled accounts) or enrollment (everyone else) |
| `/signup` | Create an account |
| `/enroll` | Set up a Voice ID: consent, three recorded samples, confirmation (signed in only) |
| `/verify` | Read the challenge passage aloud and submit the recording (signed in only) |
| `/result` | Result of the voice check, with a breakdown per check (signed in only) |

Any other address redirects to `/`. A signed-out visit to a signed-in screen redirects to `/signin`.

## Code layout

```
src/
  api/          calls to the backend (one file per endpoint group) and error wording
  components/   reusable pieces of the UI, each with its own CSS module
  hooks/        useChallenge (fetch and count down the passage), useRecorder (microphone)
  pages/        one component per screen
  utils/        small helpers: countdown, passage formatting, result wording
  assets/icons/ SVG icons exported from Figma
  test/         test setup and fakes
```

Tests sit next to the code they cover, as `*.test.ts(x)`.
