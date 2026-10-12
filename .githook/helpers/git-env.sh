#!/usr/bin/env bash
# ==============================================================================
# Git Environment and Helper Utilities
# ==============================================================================

# Get current branch name safely
get_current_branch() {
  local branch
  branch=$(git symbolic-ref --short -q HEAD 2>/dev/null || git rev-parse --short HEAD 2>/dev/null || echo "unknown")
  echo "$branch"
}

# Check if current commit is a merge commit or in merge state
is_merge_in_progress() {
  local git_dir
  git_dir=$(git rev-parse --git-dir 2>/dev/null)
  [ -f "$git_dir/MERGE_HEAD" ] || [ -f "$git_dir/rebase-merge/interactive" ] || [ -d "$git_dir/rebase-apply" ]
}

# List files staged for commit (excluding deleted files)
get_staged_files() {
  git diff --cached --name-only --diff-filter=ACMR 2>/dev/null
}

# Check if branch is protected (e.g., main or master)
is_protected_branch() {
  local branch="${1:-$(get_current_branch)}"
  case "$branch" in
    main|master|production|release|release/*)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}
