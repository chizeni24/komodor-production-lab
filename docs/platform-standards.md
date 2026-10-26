# Platform standards: health probes and the kaop-api service

Owner: Platform SRE. Applies to every service in cluster kaop-demo.

## Health probe policy

1. **Liveness checks the process only.** A liveness probe must never call a database, cache, queue or another
   service. If a dependency is down, restarting the caller does not fix it and adds restart back-off to recovery.
2. **Readiness checks dependencies.** A readiness probe may fail when a hard dependency is unreachable. That removes
   the pod from traffic without restarting it.
3. **Probe timeouts sit above dependency timeouts.** A probe's timeoutSeconds must be greater than the client
   timeout of any dependency it checks.
4. **Every liveness probe change needs review.** Pull requests that change a liveness or readiness probe must state
   which endpoint each probe uses and what that endpoint checks.

## Service: kaop-api

- Deployment kaop-api, namespace kaop-demo. Python HTTP API on port 8080.
- Endpoints:
  - `/healthz`: process liveness. Returns 200 while the HTTP server runs. Calls nothing else.
  - `/readyz`: dependency readiness. Returns 200 only when Redis answers; 503 otherwise.
  - `/`: a request that needs Redis.
- Hard dependency: Redis (Deployment and Service `redis`, port 6379). Client timeout 2 seconds.
- Deployed from git (`k8s/` in chizeni24/komodor-production-lab). Not managed by Helm or Argo CD; changes go
  through a pull request.

## Telemetry available for this stack

- Prometheus: kube-state-metrics and cAdvisor (restarts, memory, CPU, pod status).
- Loki: Kubernetes events only. Application stdout is not shipped; read app logs from the cluster.
- No traces, profiles or Grafana Sift.

## Runbook: kaop-api restarts while Redis is down

1. Restore Redis first: `kubectl scale deployment/redis -n kaop-demo --replicas=1`.
2. Verify: Redis pod Ready, the `redis` Service has endpoints, kaop-api `/readyz` returns 200.
3. If kaop-api was restarted by liveness during the outage, its liveness probe violates policy 1. Open a pull
   request that points liveness at `/healthz` and keeps readiness on `/readyz`.
