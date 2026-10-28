# Bringing BluePilot lateral to a fork

BluePilot's Ford lateral control lives in this repo and nowhere else. A fork (an openpilot fork with its own opendbc) carries it in one of two ways, adds a few hooks to its opendbc, and fills the library's inputs from its openpilot. This page is the how-to; [HOSTS.md](HOSTS.md) is the technical contract.

**This is a modified Ford safety model.** The panda safety allows signals and ranges that upstream's Ford safety blocks. Each fork decides whether to ship it, and with what default (bp-sunnypilot: on for every Ford; IQPilot: on for Fords, with a switch in its Vehicle settings).

## What a fork carries

| Piece | Where | Who changes it |
|---|---|---|
| The library | an unmodified copy of a release, at `<pkg>/bluepilot_lateral/` in the fork's opendbc (`<pkg>` is that opendbc's package name: `opendbc`, `iqdbc`, ...) | this repo only |
| The hooks | a few lines in the fork's opendbc (the Ford car controller, the car params structs, car init, `safety/modes/ford.h`, the safety tests) | kept in this repo per fork, sent to the fork as a PR |
| The fork's side | its openpilot fills the library's inputs every frame and shows the settings | the fork, with help from BluePilot |

## Two ways to carry the library

Both keep the library exactly as released, so there is one copy of the code to fix and every fork gets the same fix.

1. **A git submodule** at `<pkg>/bluepilot_lateral/`, pointing at a release commit. For forks that already use submodules (sunnypilot: BluePilotDev/opendbc carries it, and bp-sunnypilot pins that). Updating is moving the pointer. For BluePilotDev/opendbc and bp-sunnypilot, publishing a release here opens those PRs automatically.
2. **A stamped copy** of a release, for forks that take no submodules (IQPilot, StarPilot, FrogPilot). The folder is the release's files plus a `VERSION` file naming the release, made and checked with the two scripts below. Updating is copying the next release in.

Not supported: editing files inside the library folder, a git subtree that carries the library's history into the fork, or copying parts of the library elsewhere. A change belongs in this repo as a PR; once it's released, every fork takes the release.

## The stamp tools

Both run from a clone of this repo that has the release tag (`git fetch --tags`).

**`tools/vendor.sh <tag> <folder>`** makes `<folder>` exactly the library at `<tag>`:
- it empties the folder first, so files a release removed don't linger;
- it copies the release's files, without the library's own CI (`.github/`);
- it writes `<folder>/VERSION`: the tag and the commit, e.g. `v0.2.0 5974fca9...`.

```bash
git clone https://github.com/BluePilotDev/bluepilot-lateral.git
cd bluepilot-lateral
tools/vendor.sh v0.2.0 ~/iqpilot/artifacts/package_sources/iqdbc/iqdbc/bluepilot_lateral
```

Then commit the folder in the fork and open the PR. To update, run it again with the new tag: the PR shows exactly what changed between the two releases.

**`tools/check_vendored.sh <folder>`** reads `<folder>/VERSION` and compares the folder with that release, file by file (Python caches ignored). It lists every added, removed or changed file and exits non-zero if there is one:

```bash
tools/check_vendored.sh ~/iqpilot/artifacts/package_sources/iqdbc/iqdbc/bluepilot_lateral
```

A fork can run it in its own CI. It doesn't have to: once a fork carries a stamped copy, this repo's nightly check for that fork runs it and opens an issue if the copy has been edited.

## The hooks and the checks, per fork

- **sunnypilot:** the hooks are BluePilotDev/opendbc's changes to sunnypilot/opendbc. `tools/make_hook_patch.sh` prints them as one patch, attached to each release, and this repo's CI (`./test.sh`, `safety`, `bluepilot-safety`) runs on sunnypilot/opendbc with that patch.
- **IQPilot:** the hooks are `hosts/iqpilot/hooks.patch`, kept here until IQPilot carries them. `hosts/iqpilot/host.sh tree <dir>` builds IQPilot's opendbc from IQ.Lvbs's repo at a pinned commit with the hooks and the library (placed by `vendor.sh`); `host.sh test <dir>` runs the library tests, IQPilot's safety suite with the BluePilot safety tests, and coverage; `host.sh make <dir>` writes the patch back after a hook is edited in `<dir>/host`. CI's `iqpilot` job runs it on every PR, and `iqpilot pin check` tries IQ.Lvbs's latest `beta` every night: a pass moves the pin, a failure opens one issue.

A fork's adapter (`hosts/<fork>/`) lives in this repo only if this repo's CI tests the library on that fork.

## Adding a fork

1. An issue in this repo's Phase 3 milestone, "Host: <fork>": where its source and integration branch are, how it carries its opendbc (submodule or not), and how it takes outside changes.
2. The adapter in `hosts/<fork>/`, and host bindings if its safety names differ from sunnypilot's ([HOSTS.md](HOSTS.md), "Host bindings").
3. The hooks, written and tested in the fork, then kept here as `hosts/<fork>/hooks.patch` with a `host.sh` like IQPilot's.
4. A CI job and a nightly pin check for the fork, like `iqpilot`.
5. A release that contains all of it, then the PR to the fork: the hooks, its settings UI, and the library at that release (submodule or stamped copy).

Lateral changes and changes to the library's safety headers are driven on bp-sunnypilot before they're released.
