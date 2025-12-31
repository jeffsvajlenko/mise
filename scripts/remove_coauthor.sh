#!/bin/bash
# Remove Co-Authored-By from recent commits

set -e

echo "This will rewrite the last 2 commits to remove Co-Authored-By lines"
echo "Press Ctrl+C to cancel, or Enter to continue..."
read

# Create backup branch
git branch backup-before-rewrite 2>/dev/null || true

# Rewrite commits using filter-branch
git filter-branch -f --msg-filter '
  # Remove the Claude Code attribution lines
  sed "/🤖 Generated with \[Claude Code\]/d" | \
  sed "/Co-Authored-By: Claude Sonnet/d" | \
  # Remove empty lines at the end
  awk "BEGIN{RS=\"\"; ORS=\"\n\n\"} {print}" | \
  sed "$ s/\n*$/\n/"
' HEAD~2..HEAD

echo ""
echo "✓ Commits rewritten successfully"
echo ""
echo "Backup created at: backup-before-rewrite"
echo ""
echo "To push changes:"
echo "  git push --force-with-lease origin master"
echo ""
echo "To undo this rewrite:"
echo "  git reset --hard backup-before-rewrite"
echo "  git branch -D backup-before-rewrite"
