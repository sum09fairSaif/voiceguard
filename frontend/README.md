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
| `/signin` | Sign in with email and password, then go on to the voice check |
| `/signup` | Create an account |
| `/enroll` | Set up a Voice ID: consent, three recorded samples, confirmation (signed in only) |
| `/verify` | Read the challenge passage aloud and submit the recording (signed in only) |
| `/result` | Result of the voice check, with a breakdown per check (signed in only) |

Any other address, and a signed-out visit to a signed-in screen, redirects to `/signin`.

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
