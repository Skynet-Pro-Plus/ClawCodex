#!/usr/bin/env bash
# Run VERIFY_CMD until it succeeds, asking claw to fix failures between attempts.
#
# From the rust/ directory, after `cargo build -p rusty-claude-cli`:
#   ./scripts/fix_until_green.sh [max_iterations]
#
# Environment:
#   VERIFY_CMD   command to gate success (default: cargo test --workspace)
#   CLAW_BIN     path to claw executable (default: ./target/debug/claw)
#   MODEL        if set, passed as --model to claw
#
# Auto-approves permission prompts (no interactive y/N) via --auto-approve-permissions.

set -euo pipefail

max_iterations="${1:-8}"
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
rust_root="$(cd "${script_dir}/.." && pwd)"
cd "${rust_root}"

verify_cmd="${VERIFY_CMD:-cargo test --workspace}"
claw_bin="${CLAW_BIN:-./target/debug/claw}"
export CLAW_AUTO_APPROVE_PERMISSIONS="${CLAW_AUTO_APPROVE_PERMISSIONS:-1}"

model_args=()
if [[ -n "${MODEL:-}" ]]; then
  model_args=(--model "${MODEL}")
fi

if [[ ! -f "${claw_bin}" ]]; then
  echo "error: claw binary not found at ${claw_bin} (build with: cargo build -p rusty-claude-cli)" >&2
  exit 1
fi

for ((i = 1; i <= max_iterations; i++)); do
  echo "== verify (attempt ${i}/${max_iterations}): ${verify_cmd} =="
  if bash -c "${verify_cmd}"; then
    echo "== verify passed =="
    exit 0
  fi
  echo "== verify failed; sending fix prompt to claw =="
  "${claw_bin}" "${model_args[@]}" \
    --permission-mode danger-full-access \
    --auto-approve-permissions \
    prompt "Verification failed on attempt ${i} of ${max_iterations}. Command run: ${verify_cmd}

Read the failure output from the shell above (or re-run the verify command with bash if you need fresh output). Apply minimal code changes to fix the failures. Do not ask me questions; complete the work in this turn using tools. When done, reply with a one-line summary of what you fixed."
done

echo "== exhausted ${max_iterations} iterations; final verify =="
bash -c "${verify_cmd}"
