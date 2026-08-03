#!/usr/bin/env bash
# Reachability + latency smoke (P1): clean golden sample must go all-green
# through the deployed API path, inside the 5s budget.
# N1 additions (PLAN-enrichment AD-34/AD-40): healthz schema fields, and the
# poll-until-settled loop — the back-compat regression test for the explicit
# finality contract (a settled POST must say so; a provisional one must
# settle via GET within the budget window).
set -e
BASE=${BASE:-http://localhost:8123}

HEALTH=$(curl -sf $BASE/healthz)
echo "$HEALTH" | grep -q '"state"' || { echo "SMOKE FAIL: healthz missing state field"; exit 1; }
echo "$HEALTH" | grep -q '"queue"' || { echo "SMOKE FAIL: healthz missing queue field"; exit 1; }

APP='{"beverage_type":"distilled_spirits","brand_name":"OLD TOM DISTILLERY","class_type":"Kentucky Straight Bourbon Whiskey","alcohol_content":"45% Alc./Vol.","net_contents":"750 mL"}'
START=$(date +%s%N)
OUT=$(curl -sf -F "image=@api/eval/golden/spirits_clean.jpg" -F "application=$APP" $BASE/api/verify)
# poll until settled (AD-34) — no-op today (N1 settles inline), load-bearing at N3
RID=$(echo "$OUT" | sed -n 's/.*"result_id": *"\([^"]*\)".*/\1/p')
if [ -n "$RID" ] && ! echo "$OUT" | grep -q '"settled": *true'; then
  for _ in $(seq 1 20); do
    OUT=$(curl -sf "$BASE/api/verify/$RID")
    echo "$OUT" | grep -q '"settled": *true' && break
    sleep 0.25
  done
fi
MS=$(( ($(date +%s%N) - START) / 1000000 ))
echo "$OUT" | grep -q '"settled": *true' || { echo "SMOKE FAIL: result never settled"; exit 1; }
echo "$OUT" | grep -q '"screening_result": *"no_mismatch_found"' || echo "$OUT" | grep -q '"screening_result":"no_mismatch_found"' || { echo "SMOKE FAIL: clean sample not all-green"; exit 1; }
[ "$MS" -lt 5000 ] || { echo "SMOKE FAIL: ${MS}ms exceeds 5s budget"; exit 1; }
echo "SMOKE PASS: all-green, settled in ${MS}ms"
