#!/usr/bin/env bash
# BluePilot: IQPilot as a test host for this library (#18). Its opendbc, iqdbc, comes from IQ.Lvbs's own repo at the
# commit pinned below, with IQPilot's hooks (hooks.patch, the files they change outside the library) and this
# library at iqdbc/bluepilot_lateral/.
#   host.sh tree <dir> [ref]  <dir>/iq: the IQPilot folders iqdbc's code imports; <dir>/host: iqdbc on its own, a git
#                             repo with IQPilot as committed (first commit) and the hooks plus the library (second)
#   host.sh test <dir>        build <dir>/host and run the library tests, IQPilot's safety suite with the BluePilot
#                             safety tests, and 100% line coverage of modes/ford.h and the library's safety headers
#   host.sh make <dir>        write hooks.patch from <dir>/host: every change outside the library since IQPilot's
#                             commit, committed or not. Change a hook: tree, edit <dir>/host, test, make.
set -euo pipefail

REPO=https://gitlvb.teallvbs.xyz/IQ.Lvbs/IQ.Pilot.git
PIN=14e289bfd346b7d2048d8a416c6be92b8a0db3d2  # beta, 2026-10-27
PROJECT=artifacts/package_sources/iqdbc        # iqdbc's own project: setup.sh, pyproject.toml, uv.lock
IMPORTED="iqpilot/common iqpilot/cereal iqpilot/system iqpilot/selfdrive"  # imported by iqdbc's code and tests
EXTRA_PACKAGES="pyserial setproctitle"          # imported too, but only in IQPilot's top-level lock

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB="$(cd "$HERE/../.." && pwd)"
DIR="$(mkdir -p "$2" && cd "$2" && pwd)"

case "$1" in
tree)
  REF=${3:-$PIN}
  rm -rf "$DIR/iq" "$DIR/host"
  GIT_LFS_SKIP_SMUDGE=1 git clone -q --filter=blob:none --no-checkout "$REPO" "$DIR/iq"
  # shellcheck disable=SC2086 # a list of paths
  git -C "$DIR/iq" sparse-checkout set $PROJECT $IMPORTED
  GIT_LFS_SKIP_SMUDGE=1 git -C "$DIR/iq" checkout -q "$REF"
  # iqdbc on its own: under IQPilot's root, uv takes it for a member of IQPilot's workspace
  cp -R "$DIR/iq/$PROJECT" "$DIR/host"
  cd "$DIR/host"
  git init -q
  git add -A
  git -c user.name=ci -c user.email=ci@localhost commit -q -m "IQPilot $(git -C "$DIR/iq" rev-parse --short HEAD)"
  git apply "$HERE/hooks.patch"
  mkdir -p iqdbc/bluepilot_lateral
  git -C "$LIB" archive HEAD | tar -x -C iqdbc/bluepilot_lateral
  rm -rf iqdbc/bluepilot_lateral/.github
  git add -A
  git -c user.name=ci -c user.email=ci@localhost commit -q -m "hooks and library"
  echo "IQPilot $(git -C "$DIR/iq" rev-parse --short HEAD), hook patch ($(grep -c '^diff --git' "$HERE/hooks.patch") files), library $(git -C "$LIB" rev-parse --short HEAD)"
  ;;
test)
  cd "$DIR/host"
  set +u
  # shellcheck disable=SC1091 # IQPilot's: tools (clang-18 and mull on Linux, for the coverage build) and the venv
  source setup.sh
  set -u
  export PYTHONPATH="$DIR/host:$DIR/iq"  # setup.sh sets it to iqdbc alone; its code imports iqpilot too
  # shellcheck disable=SC2086 # a list of packages
  uv pip install -q $EXTRA_PACKAGES
  scons -j"$(nproc 2>/dev/null || sysctl -n hw.ncpu)"
  python -m unittest discover -s iqdbc/bluepilot_lateral/tests -t .
  # IQPilot's safety suite as its test.sh runs it (pytest: unittest also collects its base classes), the BluePilot
  # tests in the same run (its cross-mode TX sweep reads every Test* class it collects), minus IQPilot's own failures
  deselect=()
  # pytest names a test from its rootdir (iqdbc's project), not from the directory it runs in
  while read -r t; do deselect+=("--deselect=iqdbc/safety/tests/$t"); done < <(grep -v -e '^#' -e '^$' "$HERE/known_failures.txt")
  cd iqdbc/safety/tests
  rm -f libsafety/*.gcda
  pytest -q -n8 --ignore-glob='misra/*' "${deselect[@]}" . ../../bluepilot_lateral/safety/tests
  if [ "$(uname)" = "Darwin" ]; then GCOV_EXEC="/opt/homebrew/opt/llvm@18/bin/llvm-cov gcov"; else GCOV_EXEC="llvm-cov-18 gcov"; fi
  # two reports: modes/ford.h and the library's safety/ford.h share a file name (see bluepilot_coverage.sh)
  gcovr -r .. --gcov-executable "$GCOV_EXEC" --fail-under-line=100 -f "$DIR/host/iqdbc/safety/modes/ford.h"
  gcovr -r "$DIR/host" --gcov-executable "$GCOV_EXEC" -d --fail-under-line=100 -f "$DIR/host/iqdbc/bluepilot_lateral/safety/"
  ;;
make)
  git -C "$DIR/host" diff HEAD~1 -- . ':(exclude)iqdbc/bluepilot_lateral' > "$HERE/hooks.patch"
  echo "hooks.patch: $(grep -c '^diff --git' "$HERE/hooks.patch") files"
  ;;
*)
  echo "usage: $0 tree|test|make <dir> [ref]" >&2
  exit 2
  ;;
esac
