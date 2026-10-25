# Short commands for presenting the lab. Load with: source ~/komodor-demo/scripts/lab-shortcuts.sh
LAB_DIR="$HOME/komodor-demo"

lab-check() {   # is everything ready? (read-only)
  (cd "$LAB_DIR" && ./scripts/demo.sh preflight && python3 scripts/grafana_lab.py status | head -1 \
    && kubectl get pods -n kaop-agents --no-headers && free -h | awk 'NR==2{print "memory available: "$7}')
}
lab-break() {   # start the incident: Redis down until someone restores it (30 min cap)
  (cd "$LAB_DIR" && ./scripts/demo.sh outage --approve-live-mutation --max-seconds 1800)
}
lab-fix() {     # the fix KAOP proposes: bring Redis back
  kubectl scale deployment/redis -n kaop-demo --replicas=1
}
lab-pr() {      # open the one-line fix as a pull request
  (cd "$LAB_DIR" && gh pr create --repo chizeni24/komodor-production-lab --base main --head fix/decouple-liveness \
    --title "Decouple API liveness from Redis" --body-file docs/fix-pr-body.md)
}
lab-proof() {   # what the KAOP agent can and cannot do in Kubernetes
  cat "$LAB_DIR/artifacts/agent-rbac.txt"
}
lab-pods() {    # the app at a glance
  kubectl get pods -n kaop-demo
}
lab-reset() {   # emergency: bring everything back
  (cd "$LAB_DIR" && ./scripts/demo.sh reset --approve-live-mutation)
}
lab-help() {
  echo "lab-check  lab-break  lab-fix  lab-pr  lab-proof  lab-pods  lab-reset"
}
