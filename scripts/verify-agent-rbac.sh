#!/usr/bin/env bash
# Prove what a KAOP agent's Kubernetes identity can and cannot do. Read-only: uses
# `kubectl auth can-i --as`, which asks the API server and changes nothing.
#
#   scripts/verify-agent-rbac.sh <agent-namespace> <service-account> [report-file]
set -euo pipefail
NS="${1:?agent namespace, e.g. kaop-agents}"
SA="${2:?service account name of the Kubernetes RCA agent}"
OUT="${3:-artifacts/agent-rbac.txt}"
K=(kubectl --kubeconfig="${KUBECONFIG_LAB:-$HOME/.kube/kaop-demo-rootful.yaml}" --context=kind-kaop-demo)
WHO="system:serviceaccount:${NS}:${SA}"

checks=(
  "get pods -n kaop-demo|yes"
  "list events -n kaop-demo|yes"
  "get pods/log -n kaop-demo|yes"
  "get deployments -n kaop-demo|yes"
  "get replicasets -n kaop-demo|yes"
  "list nodes|yes"
  "get secrets -n kaop-demo|no"
  "create pods/exec -n kaop-demo|no"
  "delete pods -n kaop-demo|no"
  "patch deployments -n kaop-demo|no"
  "update deployments/scale -n kaop-demo|no"
  "create deployments -n kaop-demo|no"
)

mkdir -p "$(dirname "$OUT")"
fail=0
report="$(mktemp)"
{
  echo "Kubernetes permissions of ${WHO}  ($(date -u +%FT%TZ))"
  printf '%-38s %-8s %-8s %s\n' "ACTION" "EXPECTED" "ACTUAL" "RESULT"
  for entry in "${checks[@]}"; do
    action="${entry%%|*}"; expected="${entry##*|}"
    # shellcheck disable=SC2086
    actual="$("${K[@]}" auth can-i $action --as="$WHO" 2>/dev/null || true)"
    actual="${actual:-no}"
    if [[ "$actual" == "$expected" ]]; then result="ok"; else result="UNEXPECTED"; fail=1; fi
    printf '%-38s %-8s %-8s %s\n' "$action" "$expected" "$actual" "$result"
  done
} > "$report"
cp "$report" "$OUT" && rm -f "$report"
cat "$OUT"
echo "Saved: $OUT"
exit "$fail"
