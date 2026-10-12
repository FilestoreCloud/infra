#!/usr/bin/env bash
# ==============================================================================
# Security and Cleanliness Guard for Staged Files
# ==============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/colors.sh"
source "$SCRIPT_DIR/git-env.sh"

check_staged_security() {
  local staged_files
  staged_files=$(get_staged_files)

  if [ -z "$staged_files" ]; then
    return 0
  fi

  local failed=0

  # 1. Check for accidental staging of secret files
  for file in $staged_files; do
    case "$file" in
      *.pem|*.key|*.pkcs12|*.pfx|*.cert|id_rsa|id_dsa|id_ed25519)
        log_error "Blocked: Detected private key or certificate staged: $file"
        failed=1
        ;;
      .env|.env.local|.env.production|.env.staging)
        log_error "Blocked: Detected environment secret file staged: $file"
        failed=1
        ;;
      *credentials.json|*client_secrets.json)
        log_error "Blocked: Detected credentials file staged: $file"
        failed=1
        ;;
    esac
  done

  # 2. Check for unresolved Git merge conflict markers in text files
  local conflict_files
  conflict_files=$(git diff --cached -S"<<<<<<< " --name-only 2>/dev/null | grep -v '^\.githook/' || true)
  if [ -n "$conflict_files" ]; then
    log_error "Unresolved merge conflict markers found in:"
    for cf in $conflict_files; do
      printf "    - %s\n" "$cf"
    done
    failed=1
  fi

  # 3. Check for obvious hardcoded AWS access keys in staged code
  local aws_key_hits
  aws_key_hits=$(git diff --cached -G"(AKIA|ABIA|ACCA|ASIA)[0-9A-Z]{16}" --name-only 2>/dev/null | grep -v '^\.githook/' || true)
  if [ -n "$aws_key_hits" ]; then
    log_error "Potential hardcoded AWS Access Key ID detected in staged files:"
    for hit in $aws_key_hits; do
      printf "    - %s\n" "$hit"
    done
    log_warn "If this is intentional or a mock string in tests, bypass using '--no-verify'."
    failed=1
  fi

  if [ "$failed" -ne 0 ]; then
    return 1
  fi

  return 0
}
