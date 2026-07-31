#!/usr/bin/env bash
# Reachability + latency smoke (P1): clean golden sample must go all-green
# through the deployed API path, inside the 5s budget.
set -e
BASE=${BASE:-http://localhost:8123}
APP='{"beverage_type":"distilled_spirits","brand_name":"OLD TOM DISTILLERY","class_type":"Kentucky Straight Bourbon Whiskey","alcohol_content":"45% Alc./Vol.","net_contents":"750 mL"}'
START=$(date +%s%N)
OUT=$(curl -sf -F "image=@api/eval/golden/spirits_clean.jpg" -F "application=$APP" $BASE/api/verify)
MS=$(( ($(date +%s%N) - START) / 1000000 ))
echo "$OUT" | grep -q '"screening_result": *"no_mismatch_found"' || echo "$OUT" | grep -q '"screening_result":"no_mismatch_found"' || { echo "SMOKE FAIL: clean sample not all-green"; exit 1; }
[ "$MS" -lt 5000 ] || { echo "SMOKE FAIL: ${MS}ms exceeds 5s budget"; exit 1; }
echo "SMOKE PASS: all-green in ${MS}ms"
