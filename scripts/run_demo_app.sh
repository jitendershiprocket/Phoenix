#!/usr/bin/env bash
# Run Phoenix agent for demo-app (Sentry project: demo-app)
# Always fresh clone from https://github.com/jitendershiprocket/demo-app (branch: main)
# Usage: ./scripts/run_demo_app.sh  OR  bash scripts/run_demo_app.sh

cd "$(dirname "$0")/.." || exit 1
rm -rf workspace/demo-app
python -m src.main --from-sentry --project demo-app "$@"
