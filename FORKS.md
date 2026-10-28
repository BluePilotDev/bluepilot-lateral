# Bringing BluePilot lateral to a fork

How an openpilot fork takes BluePilot's Ford lateral control from this library, and how it works with BluePilot after that. [HOSTS.md](HOSTS.md) is the technical contract: the inputs, settings and safety bits a host provides.

**This is a modified Ford safety model.** The panda safety allows signals and ranges that upstream's Ford safety blocks. Each fork decides whether to ship it, and whether BluePilot lateral is on or off by default for its users.

## What a fork carries

| Piece | Where | Who changes it |
|---|---|---|
| The library | an unmodified copy of a release, at `<pkg>/bluepilot_lateral/` in the fork's opendbc (`<pkg>` is that opendbc's package name) | this repo only |
| The hooks | a few lines in the fork's opendbc: the Ford car controller, the car params structs, car init, `safety/modes/ford.h`, the safety tests | kept in this repo, sent to the fork as a PR |
| The fork's side | its openpilot fills the library's inputs every frame and shows the settings | the fork, with BluePilot's help |

## Carrying the library

The library is always an exact copy of a release. There is one copy of the code to fix, and every fork gets the same fix.

1. **A git submodule** at `<pkg>/bluepilot_lateral/`, pointing at a release commit, for a fork that uses submodules. Updating is moving the pointer.
2. **A stamped copy** of a release, for a fork that takes no submodules: the release's files plus a `VERSION` file naming the release, made and checked with the stamp tools below. Updating is copying the next release in.

Not accepted:
- editing files inside the library folder;
- a git subtree that carries the library's history into the fork;
- copying parts of the library somewhere else.

A change to the library is a PR to this repo. Once it's released, every fork takes the release.

## The stamp tools

Both run from a clone of this repo that has the release tag (`git fetch --tags`).

**`tools/vendor.sh <tag> <folder>`** makes `<folder>` exactly the library at `<tag>`:
- it empties the folder first, so files a release removed don't linger;
- it copies the release's files, without the library's own CI (`.github/`);
- it writes `<folder>/VERSION`: the tag and the commit, e.g. `v1.2.3 0a1b2c3d...`.

```bash
git clone https://github.com/BluePilotDev/bluepilot-lateral.git
cd bluepilot-lateral
tools/vendor.sh <tag> <fork checkout>/<path to its opendbc package>/bluepilot_lateral
```

Commit the folder in the fork and open the PR. To update, run it again with the new tag: the PR shows exactly what changed between the two releases.

**`tools/check_vendored.sh <folder>`** reads `<folder>/VERSION` and compares the folder with that release, file by file (Python caches ignored). It lists every added, removed or changed file, and exits non-zero if there is one:

```bash
tools/check_vendored.sh <fork checkout>/<path to its opendbc package>/bluepilot_lateral
```

A fork may run it in its own CI. It doesn't have to: this repo checks every stamped copy it knows of every night, and opens an issue if one has been edited.

## What BluePilot keeps for each fork

For every fork it supports, this repo keeps:
- **an adapter**, `hosts/<fork>/`, that hands the library the fork's types, plus host bindings if the fork's safety names differ from upstream's ([HOSTS.md](HOSTS.md), "Host bindings");
- **the fork's hooks**, `hosts/<fork>/hooks.patch`, until the fork carries them;
- **`hosts/<fork>/host.sh`**: `tree <dir>` builds the fork's opendbc at a pinned commit with the hooks and the library, placed by `vendor.sh`; `test <dir>` runs the library tests, the fork's safety suite with the BluePilot safety tests, and coverage; `make <dir>` writes `hooks.patch` back after a hook is edited in `<dir>/host`;
- **a CI job** that runs `host.sh tree` and `test` on every PR to this repo;
- **a nightly check** that tries the fork's latest integration branch: a pass moves the pinned commit, a failure opens one issue saying which step broke. Once the fork carries the hooks, it tests the fork's tree as it is, and runs `check_vendored.sh` on its copy.

An adapter lives in this repo only if this repo's CI tests the library on that fork.

## Adding a fork

1. Open an issue in this repo, "Host: <fork>": where the fork's source and integration branch are, how it carries its opendbc, and how it takes outside changes.
2. Write and test the hooks and the fork's side in the fork.
3. Add the adapter, `hooks.patch`, `host.sh`, the CI job and the nightly check here, in one PR.
4. Release the library with them.
5. Open the PR to the fork: the hooks, its settings UI, and the library at that release, as a submodule or a stamped copy.

## Changes and releases

- Lateral changes and changes to the library's safety headers are driven on a car before they're released.
- Every release says what changed in the lateral control, the CAN messages and the panda safety, and what was validated.
- A fork takes a release when it chooses to; BluePilot opens the PR for it.
