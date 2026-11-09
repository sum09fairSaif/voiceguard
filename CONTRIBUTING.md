# Contributing to VoiceGuard

## Branches

- `main` is always deployable. Nobody pushes to it directly.
- `dev` is the integration branch. Everything merges here first.
- Work happens on a short-lived branch off `dev`, named by type:
  - `feature/<story-number>-short-name` for a user story, e.g. `feature/12-log-in-with-voice`
    (`feature/`, not `feat/`: `feat` is the commit type, `feature/` the branch prefix)
  - `fix/<issue-number>-short-name` for a bug fix, e.g. `fix/118-contrast-small-screens`
  - `chore/short-name`, `docs/short-name` or `ci/short-name` for upkeep
- Branch names are lowercase words joined by hyphens.
- Delete the branch once its pull request has merged.

## Commit messages

Use the form `type: what the commit does`, in the present tense:

```
feat: add password sign-in with lockout after 5 failed attempts
fix: release the microphone when leaving the passage screen
test: cover expired passages
docs: add setup steps to the README
chore: ignore voice recordings
ci: run the frontend tests
```

- Types: `feat`, `fix`, `test`, `docs`, `chore`, `ci`, `refactor`.
- Keep the first line under about 72 characters. Put the details (the why)
  in the body, after a blank line.
- One logical change per commit where you can.

## Pull requests

1. Push your branch and open a pull request into `dev`.
2. Fill in the pull request template: the user story it belongs to,
   acceptance criteria, screenshots for screen changes, and how it was tested.
3. Title it like a commit message, e.g. `feat: add enrollment screen [#10]`.
4. It needs **one approving review from a teammate** and **green CI** before
   it merges. Reviewers: read the change, try it if it touches a screen, and
   leave at least one comment or question.
5. Keep pull requests small: one user story, or one fix, per pull request.

Releasing to `main`: open a pull request from `dev` into `main` titled
`release: <what's included>`, listing the pull requests it brings in.

## Code review

- Be kind and specific. Comment on the code, not the person.
- The author merges once the review is approved and CI passes.

## Before you push

Run the checks for each folder you changed, each line from the repository
root. CI runs the same ones on every pull request.

```
cd backend && python -m pytest && ruff check .
cd frontend && npm run lint && npm test && npm run build
cd model-service && python -m pytest && ruff check .
cd ml/liveness && python -m pytest
```

Never commit secrets (`.env`, API keys, tokens) or voice recordings. Both
are git-ignored; if `git status` shows one, stop and check why.
