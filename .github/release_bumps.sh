#!/usr/bin/env bash
# A library release, through to a bp-sunnypilot PR (spec: ford-op/bg-opendbc#97). Bumps the library in
# bg-opendbc and merges that PR once its required checks pass (nothing else auto-merges there), then
# opens the bp-sunnypilot PR that moves opendbc_repo to the new bg-clean, saying whether it changes the
# panda firmware or the lateral Python (a drive before merge if so). Not merged automatically.
# usage: GH_TOKEN=<ford-op-sync App token for bg-opendbc and bp-sunnypilot> release_bumps.sh <tag> <commit>
set -euo pipefail
TAG=$1 SHA=$2
LIB=$(pwd)
WORK=$(mktemp -d)
git config --global user.name "ford-op-sync[bot]"
git config --global user.email "ford-op-sync[bot]@users.noreply.github.com"
clone() {  # <repo> <branch> <dir>: history and trees only, no checkout, index at HEAD
  GIT_LFS_SKIP_SMUDGE=1 git -c filter.lfs.process= -c filter.lfs.required=false clone -q --filter=blob:none \
    --no-checkout -b "$2" "https://x-access-token:${GH_TOKEN}@github.com/ford-op/$1.git" "$3"
  git -C "$3" read-tree HEAD
}
bump() {  # <dir> <path> <commit> <branch> <message>: commit a new gitlink and push it as <branch>
  git -C "$1" update-index --cacheinfo "160000,$3,$2"
  git -C "$1" -c filter.lfs.process= -c filter.lfs.required=false commit -q -m "$5"
  git -C "$1" push -q origin "HEAD:refs/heads/$4"
}

# 1. bg-opendbc: the library pointer, merged on green
clone bg-opendbc bg-clean "$WORK/bg"
if [ "$(git -C "$WORK/bg" rev-parse HEAD:opendbc/bluepilot_lateral)" = "$SHA" ]; then
  echo "bg-opendbc already pins $TAG"
  BG=$(git -C "$WORK/bg" rev-parse HEAD)
else
  BRANCH="bump/library-$TAG"
  bump "$WORK/bg" opendbc/bluepilot_lateral "$SHA" "$BRANCH" "bluepilot_lateral: bump to $TAG"
  PR=$(gh pr create -R ford-op/bg-opendbc -B bg-clean -H "$BRANCH" --title "bluepilot_lateral: bump to $TAG" --body \
"The library pointer moves to bluepilot-lateral [$TAG](https://github.com/ford-op/bluepilot-lateral/releases/tag/$TAG) (${SHA:0:8}). Opened by the library's release job, which merges it once the required checks pass (ford-op/bg-opendbc#97).

## Validation
- [ ] CI \`./test.sh (Linux)\`
- [ ] CI \`safety\`
- [ ] CI \`bluepilot-safety\`
- [ ] CI \`bluepilot-hooks\`")
  echo "bg-opendbc: $PR"
  # the checks take a moment to register; then wait for the required ones
  for _ in $(seq 60); do
    rc=0; gh pr checks "$PR" --required >/dev/null 2>&1 || rc=$?
    [ "$rc" = 0 ] || [ "$rc" = 8 ] && break
    sleep 10
  done
  gh pr checks "$PR" --required --watch --fail-fast --interval 30
  gh pr checks "$PR" --required  # exits non-zero unless every required check passed
  gh pr view "$PR" --json body -q .body | sed 's/^- \[ \] CI/- [x] CI/' > "$WORK/body.md"
  gh pr edit "$PR" --body-file "$WORK/body.md"
  gh pr merge "$PR" --squash --delete-branch
  BG=$(gh pr view "$PR" --json mergeCommit -q .mergeCommit.oid)
  git -C "$WORK/bg" fetch -q origin bg-clean
fi

# 2. bp-sunnypilot: opendbc_repo to that bg-clean, as a PR
clone bp-sunnypilot master-local-lateral "$WORK/sp"
OLD=$(git -C "$WORK/sp" rev-parse HEAD:opendbc_repo)
if [ "$OLD" = "$BG" ]; then echo "bp-sunnypilot already at ${BG:0:8}"; exit 0; fi
OLDLIB=$(git -C "$WORK/bg" rev-parse "$OLD:opendbc/bluepilot_lateral")
changed() {  # what moved: bg-opendbc outside the library, then the library itself
  git -C "$WORK/bg" diff --name-only "$OLD" "$BG" -- . ':!opendbc/bluepilot_lateral'
  git -C "$LIB" diff --name-only "$OLDLIB" "$SHA" | sed 's|^|opendbc/bluepilot_lateral/|'
}
FILES=$(changed)
FW=$(grep -E '\.(h|c)$' <<<"$FILES" || true)
LAT=$(grep -E '^opendbc/bluepilot_lateral/.*\.py$|^opendbc/car/ford/.*\.py$|^opendbc/car/structs\.py$|^opendbc/sunnypilot/car/interfaces\.py$' <<<"$FILES" | grep -v '/tests/' || true)
# shellcheck disable=SC2016  # the backticks are Markdown, not expansions
list() { if [ -n "$1" ]; then sed 's/^/  - `/; s/$/`/' <<<"$1"; else echo "  - none"; fi; }
DRIVE=""
[ -n "$FW$LAT" ] && DRIVE="
- [ ] A drive (panda firmware or lateral Python changed)"
BRANCH="opendbc/library-$TAG"
bump "$WORK/sp" opendbc_repo "$BG" "$BRANCH" "opendbc_repo: bg-clean ${BG:0:8} (bluepilot-lateral $TAG)"
gh pr create -R ford-op/bp-sunnypilot -B master-local-lateral -H "$BRANCH" \
  --title "opendbc_repo: bluepilot-lateral $TAG" --body \
"\`opendbc_repo\` moves to bg-opendbc \`bg-clean\` ${BG:0:8}, which has bluepilot-lateral [$TAG](https://github.com/ford-op/bluepilot-lateral/releases/tag/$TAG). Opened by the library's release job (ford-op/bg-opendbc#97); not merged automatically.

- Panda firmware (\`.h\`/\`.c\`) changed:
$(list "$FW")
- Lateral Python changed (outside tests):
$(list "$LAT")

## Validation
- [ ] CI \`build release\`
- [ ] CI \`build macOS\`
- [ ] CI \`static analysis\`
- [ ] CI \`unit tests\`
- [ ] CI \`process replay\`: only the known Ford segment differs (\`regen755D8CB1E1F\`, \`card\` \`sendcan\`)$DRIVE"
