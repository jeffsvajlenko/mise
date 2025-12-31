#!/bin/bash
# Remove Co-Authored-By from recent commits (non-interactive)

set -e

echo "Rewriting the last 2 commits to remove Co-Authored-By lines..."

# Create backup branch
git branch backup-before-rewrite 2>/dev/null || true
echo "✓ Backup created at: backup-before-rewrite"

# Rewrite commits using filter-branch
git filter-branch -f --msg-filter '
  # Remove the Claude Code attribution lines
  sed "/🤖 Generated with \[Claude Code\]/d" | \
  sed "/Co-Authored-By: Claude Sonnet/d" | \
  # Remove trailing blank lines
  sed -e :a -e "/^\n*$/{$d;N;ba" -e "}"
' HEAD~2..HEAD 2>&1 | grep -v "WARNING: git-filter-branch" || true

echo ""
echo "✓ Commits rewritten successfully"
echo ""
echo "To push changes:"
echo "  git push --force-with-lease origin master"
echo ""
echo "To undo this rewrite:"
echo "  git reset --hard backup-before-rewrite"
echo "  git branch -D backup-before-rewrite"
