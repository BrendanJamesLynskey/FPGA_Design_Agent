#!/usr/bin/env bash
# Install OCaml 5.3.0 and Hardcaml user-local (brief 171). No sudo, no system packages beyond libgmp-dev and m4
# (zarith needs the GMP headers; opam needs m4 for some packages). Safe to re-run.
# Pinned: opam 2.6.1 (binary at ~/.local/opt/opam-bin/opam, GPG-verified at download), OCaml 5.3.0, Hardcaml v0.17.1,
# hardcaml_waveterm / hardcaml_step_testbench / hardcaml_verify v0.17.0, ppx_hardcaml v0.17.1 (dune 3.25.0 and the rest
# solved by opam on 2026-11-22 against the opam-repository of that day; `opam list` is recorded in
# docs/hardcaml_scoping.md and results/b171/opam_list.txt).
set -euo pipefail
export OPAMROOT="${OPAMROOT:-$HOME/.local/opt/opam}"
export PATH="$HOME/.local/opt/opam-bin:$PATH"
[ -d "$OPAMROOT/repo" ] || opam init --bare --disable-sandboxing -n      # -n: no shell-profile edits
if ! opam switch list --short | grep -qx hardcaml-5.3.0; then
  systemd-run --user --scope -p MemoryMax=4G nice -n 15 opam switch create hardcaml-5.3.0 ocaml-base-compiler.5.3.0 -y -j2
fi
eval "$(opam env --switch=hardcaml-5.3.0)"
systemd-run --user --scope -p MemoryMax=4G nice -n 15 opam install -y -j2 \
  hardcaml hardcaml_waveterm hardcaml_step_testbench hardcaml_verify ppx_hardcaml ppx_jane
opam list --installed --short --columns=name,installed-version > "$(dirname "$0")/../../results/b171/opam_list.txt" 2>/dev/null || true
