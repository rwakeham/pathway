#!/usr/bin/env bash
set -e

git fetch origin

# Check if the feature branch has commits not yet on main
FEATURE_BRANCH=$(git branch -r --format '%(refname:short)' | grep 'origin/claude/' | sed 's|origin/||' | head -1)

if [ -n "$FEATURE_BRANCH" ]; then
  AHEAD=$(git rev-list --count "origin/main..origin/$FEATURE_BRANCH")
else
  AHEAD=0
fi

if [ "$AHEAD" -gt 0 ]; then
  echo "Feature branch $FEATURE_BRANCH is $AHEAD commit(s) ahead of main. Merging..."
  # Create PR if one doesn't already exist, then merge it
  gh pr create --base main --head "$FEATURE_BRANCH" --title "Deploy $FEATURE_BRANCH" --body "" 2>/dev/null || true
  gh pr merge "$FEATURE_BRANCH" --squash --delete-branch=false
  # Fetch again so origin/main reflects the merge
  git fetch origin
else
  echo "Nothing to merge, deploying current main..."
fi

git checkout main
git reset --hard origin/main

# Reset the feature branch to main so it never diverges after a squash merge
if [ -n "$FEATURE_BRANCH" ]; then
  git branch -f "$FEATURE_BRANCH" main 2>/dev/null || true
  git push --force origin "$FEATURE_BRANCH"
fi

echo "Redeploying..."
docker compose up --build -d

echo "Done."
