## Problem

The API's liveness probe points at `/readyz`, which pings Redis. When Redis is unavailable, the kubelet kills a
healthy API process again and again. It did so five times in a five-minute outage during rehearsal. Each kill drops
in-flight work and adds restart back-off, and the restart alert pages the API owners for a Redis problem.

## Change

Point liveness at `/healthz`, which answers as long as the process is alive. Readiness stays on `/readyz`, so a pod
that cannot reach Redis still stops receiving traffic.

## Evidence

- Redis outage with liveness on `/readyz`: 5 liveness kills and 4 restarts in 5 minutes; Grafana restart alert fired (see `docs/evidence.md`).
- Same outage with liveness on `/healthz`: zero liveness failures, zero restarts, alert stayed Normal.
- Unit test `test_redis_outage_fails_readiness_but_not_liveness` covers the endpoint semantics.
