#!/usr/bin/env bash
# ==============================================================================
# Script: setup.sh
# Purpose: Activate .githook as the active Git hooks path for this repository
# ==============================================================================

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
HOOK_DIR="$ROOT_DIR/.githook"

source "$HOOK_DIR/helpers/colors.sh"

log_header "Activating .githook for Nextcloud Multi-Tenant SaaS"

# Ensure we are inside a Git repo
if ! git -C "$ROOT_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  log_error "Not inside a valid Git repository."
  exit 1
fi

log_step "Making all hook scripts executable..."
chmod +x "$HOOK_DIR/commit-msg" \
         "$HOOK_DIR/pre-commit" \
         "$HOOK_DIR/pre-push" \
         "$HOOK_DIR/prepare-commit-msg" \
         "$HOOK_DIR/post-merge" \
         "$HOOK_DIR/setup.sh" \
         "$HOOK_DIR/helpers/"*.sh

log_step "Configuring git core.hooksPath to .githook..."
git -C "$ROOT_DIR" config core.hooksPath .githook

CURRENT_HOOKS_PATH=$(git -C "$ROOT_DIR" config --get core.hooksPath)
log_success "Git core.hooksPath configured to: $CURRENT_HOOKS_PATH"

printf "\n${COLOR_BOLD}Active hooks:${COLOR_RESET}\n"
printf "  • ${COLOR_CYAN}commit-msg${COLOR_RESET}         : Enforces Conventional Commits specification\n"
printf "  • ${COLOR_CYAN}pre-commit${COLOR_RESET}         : Branch protection + staged secrets scan + pre-commit hooks\n"
printf "  • ${COLOR_CYAN}pre-push${COLOR_RESET}           : Protected branch guard before git push\n"
printf "  • ${COLOR_CYAN}prepare-commit-msg${COLOR_RESET} : Issue/ticket identifier helper\n"
printf "  • ${COLOR_CYAN}post-merge${COLOR_RESET}         : Dependency update & infra change notification\n"
printf "\n${COLOR_GREEN}✔ Git hooks are now active!${COLOR_RESET}\n\n"
