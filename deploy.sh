#!/usr/bin/env bash
set -e

BRANCH=$(git rev-parse --abbrev-ref HEAD)

echo "Merging $BRANCH into main..."
git checkout main
git pull
git merge --no-ff "$BRANCH" -m "Merge $BRANCH into main"
git push

echo "Redeploying..."
docker compose up --build -d

echo "Done."
