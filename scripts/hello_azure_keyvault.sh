#!/usr/bin/env bash
# Hello-world for Azure Key Vault — proves the whole vault path on your
# subscription BEFORE the DevSecOps playbook relies on it: create with a
# globally-unique name → wait for real DNS → write a secret → read it
# back → list → delete AND PURGE (soft-delete would otherwise squat the
# name — the exact failure class the playbook's 3b block recovers from).
#
# Usage:  RG=labelcheck-dev LOC=eastus ./scripts/hello_azure_keyvault.sh
# Needs:  az CLI, logged in (az login). Prints secret NAMES, never values.
set -euo pipefail

RG=${RG:-labelcheck-dev}
LOC=${LOC:-eastus}

echo "» subscription: $(az account show --query name -o tsv)"
az group create -n "$RG" -l "$LOC" -o none

# vault names: global, 3-24 chars, alnum+hyphen — subscription prefix +
# random suffix keeps this collision-proof and obviously disposable
KV="hello-kv-$(az account show --query id -o tsv | cut -c1-8)-$((RANDOM % 9000 + 1000))"
echo "» creating vault $KV"
az keyvault create -n "$KV" -g "$RG" -l "$LOC" -o none

echo "» waiting for control plane + DNS"
for i in $(seq 1 36); do
  if az keyvault show -n "$KV" -o none 2>/dev/null \
     && getent hosts "$KV.vault.azure.net" >/dev/null; then
    break
  fi
  sleep 5
  [ "$i" = 36 ] && { echo "✗ $KV.vault.azure.net never resolved"; exit 1; }
done
echo "  resolved: $KV.vault.azure.net"

echo "» write → read back"
WANT="world-$(date +%s)"
if ! az keyvault secret set --vault-name "$KV" -n hello --value "$WANT" -o none 2>/tmp/kv-err; then
  if grep -qi "forbidden\|authorization" /tmp/kv-err; then
    echo "✗ 403 — vault is in RBAC mode; grant yourself the data-plane role:"
    echo "  az role assignment create --assignee \$(az ad signed-in-user show --query id -o tsv) \\"
    echo "    --role 'Key Vault Secrets Officer' --scope \$(az keyvault show -n $KV --query id -o tsv)"
    echo "  …then re-run. Cleaning up the vault first:"
  else
    cat /tmp/kv-err
  fi
  az keyvault delete -n "$KV" -o none && az keyvault purge -n "$KV" -o none
  exit 1
fi
GOT=$(az keyvault secret show --vault-name "$KV" -n hello --query value -o tsv)
if [ "$GOT" = "$WANT" ]; then
  echo "  ✓ round trip OK (value matches; not printed)"
else
  echo "✗ read-back mismatch"; az keyvault delete -n "$KV" -o none; exit 1
fi

echo "» secrets in vault (names only): $(az keyvault secret list --vault-name "$KV" --query '[].name' -o tsv | tr '\n' ' ')"

echo "» cleanup: delete + purge (so the name is truly released)"
az keyvault delete -n "$KV" -o none
az keyvault purge -n "$KV" -o none 2>/dev/null \
  || echo "  (purge denied — purge-protection policy; the name stays soft-deleted ~90 days)"

echo "✓ Key Vault hello world complete — the playbook's step 3 will work here."
