#!/usr/bin/env bash
set -e

BRANCH=$(git rev-parse --abbrev-ref HEAD)

if [ "$BRANCH" != "main" ]; then
  echo "Merging $BRANCH into main..."
  git checkout main
  git merge --no-ff "$BRANCH" -m "Merge $BRANCH into main"
fi

echo "Redeploying..."
docker compose up --build -d

echo "Done."
