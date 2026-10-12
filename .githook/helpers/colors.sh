#!/usr/bin/env bash
# ==============================================================================
# Terminal Color & Logging Utilities for Git Hooks
# ==============================================================================

# Enable colors only if stdout is a TTY and NO_COLOR is not set
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
  COLOR_RESET="\033[0m"
  COLOR_BOLD="\033[1m"
  COLOR_RED="\033[31m"
  COLOR_GREEN="\033[32m"
  COLOR_YELLOW="\033[33m"
  COLOR_BLUE="\033[34m"
  COLOR_MAGENTA="\033[35m"
  COLOR_CYAN="\033[36m"
  COLOR_GRAY="\033[90m"
else
  COLOR_RESET=""
  COLOR_BOLD=""
  COLOR_RED=""
  COLOR_GREEN=""
  COLOR_YELLOW=""
  COLOR_BLUE=""
  COLOR_MAGENTA=""
  COLOR_CYAN=""
  COLOR_GRAY=""
fi

log_step() {
  printf "${COLOR_CYAN}➜ %s${COLOR_RESET}\n" "$*"
}

log_info() {
  printf "${COLOR_BLUE}ℹ %s${COLOR_RESET}\n" "$*"
}

log_success() {
  printf "${COLOR_GREEN}✔ %s${COLOR_RESET}\n" "$*"
}

log_warn() {
  printf "${COLOR_YELLOW}⚠ %s${COLOR_RESET}\n" "$*"
}

log_error() {
  printf "${COLOR_RED}✖ %s${COLOR_RESET}\n" "$*" >&2
}

log_header() {
  printf "\n${COLOR_BOLD}${COLOR_MAGENTA}=== %s ===${COLOR_RESET}\n" "$*"
}
