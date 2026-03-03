#!/usr/bin/env bash
# Run Phoenix agent for SR_Web (Sentry project: seller_19)
# Always fresh clone from https://github.com/jitendershiprocket/SR_Web (branch: agent_ai)
# Usage: ./scripts/run_sr_web.sh  OR  bash scripts/run_sr_web.sh

cd "$(dirname "$0")/.." || exit 1
rm -rf workspace/SR_Web
python -m src.main --from-sentry --project seller_19 "$@"
