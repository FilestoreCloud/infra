#!/usr/bin/env bash
# ==============================================================================
# Conventional Commit Message Validator
# ==============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/colors.sh"

validate_commit_message() {
  local msg_file="$1"

  if [ ! -f "$msg_file" ]; then
    log_error "Commit message file not found: $msg_file"
    return 1
  fi

  # Extract first non-comment, non-empty line
  local first_line
  first_line=$(grep -v '^[[:space:]]*#' "$msg_file" | grep -v '^[[:space:]]*$' | head -n 1)

  if [ -z "$first_line" ]; then
    log_error "Commit message cannot be empty!"
    return 1
  fi

  # Allow automated git merge commits
  if echo "$first_line" | grep -Eq '^(Merge branch|Merge pull request|Merge remote-tracking branch)'; then
    return 0
  fi

  # Allow git revert messages
  if echo "$first_line" | grep -Eq '^Revert "'; then
    return 0
  fi

  # Allow fixup! and squash! commits during rebase
  if echo "$first_line" | grep -Eq '^(fixup!|squash!)'; then
    return 0
  fi

  # Conventional commit regex pattern:
  # type(scope?)(!)?: subject
  local pattern="^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)(\([a-zA-Z0-9_./-]+\))?(!)?: .+$"

  if ! echo "$first_line" | grep -Eq "$pattern"; then
    log_error "Invalid commit message format!"
    printf "\n"
    printf "  ${COLOR_BOLD}Your message:${COLOR_RESET} \"%s\"\n\n" "$first_line"
    printf "  ${COLOR_BOLD}Required Conventional Commits format:${COLOR_RESET}\n"
    printf "    ${COLOR_CYAN}<type>(<optional-scope>): <description>${COLOR_RESET}\n"
    printf "    ${COLOR_CYAN}<type>(<optional-scope>)!: <breaking-change-description>${COLOR_RESET}\n\n"
    printf "  ${COLOR_BOLD}Allowed types:${COLOR_RESET}\n"
    printf "    • ${COLOR_GREEN}feat${COLOR_RESET}     : A new feature\n"
    printf "    • ${COLOR_GREEN}fix${COLOR_RESET}      : A bug fix\n"
    printf "    • ${COLOR_GREEN}docs${COLOR_RESET}     : Documentation changes\n"
    printf "    • ${COLOR_GREEN}style${COLOR_RESET}    : Code style / formatting (no logic change)\n"
    printf "    • ${COLOR_GREEN}refactor${COLOR_RESET} : Refactoring code without behavior change\n"
    printf "    • ${COLOR_GREEN}perf${COLOR_RESET}     : Performance improvement\n"
    printf "    • ${COLOR_GREEN}test${COLOR_RESET}     : Adding or fixing tests\n"
    printf "    • ${COLOR_GREEN}build${COLOR_RESET}    : Build system or external dependencies\n"
    printf "    • ${COLOR_GREEN}ci${COLOR_RESET}       : CI/CD configuration files and scripts\n"
    printf "    • ${COLOR_GREEN}chore${COLOR_RESET}    : Routine tasks, maintenance\n"
    printf "    • ${COLOR_GREEN}revert${COLOR_RESET}   : Reverting a previous commit\n\n"
    printf "  ${COLOR_BOLD}Examples:${COLOR_RESET}\n"
    printf "    ${COLOR_GRAY}feat(auth): add OAuth2 provider for tenants${COLOR_RESET}\n"
    printf "    ${COLOR_GRAY}fix(alb): resolve host-header routing timeout${COLOR_RESET}\n"
    printf "    ${COLOR_GRAY}docs: update multi-tenant deployment guide${COLOR_RESET}\n\n"
    return 1
  fi

  # Check subject does not end with period
  if echo "$first_line" | grep -Eq '\.$'; then
    log_warn "Commit subject should not end with a period ('.')."
  fi

  # Check line length (recommend max 72-100 characters for subject)
  local line_length=${#first_line}
  if [ "$line_length" -gt 100 ]; then
    log_warn "Commit summary line is too long (${line_length} chars, recommended <= 72)."
  fi

  return 0
}
