# Contributing to VoiceGuard

## Branches

- `main` is always deployable. Nobody pushes to it directly.
- `dev` is the integration branch. Features merge here first.
- `feature/<story-number>-short-name` is where we'll build one user story,
  branched off `dev`.

## Pull requests

1. Push your feature branch and open a pull request into `dev`.
2. A PR needs at least one approving review and green CI before it merges.
3. Keep PRs small: one user story per PR where possible.

## Commit messages

- Write in the present tense: "add login screen", not "added login screen".
- One logical change per commit where you can.

## Code review

- Be kind and specific. Comment on the code, not the person.
- The author merges once the review is approved and CI passes.