# Optional scenario: gradual memory leak

This branch keeps a second, optional fault for the KAOP incident lab. The main demo lives on
[`main`](https://github.com/chizeni24/komodor-production-lab) and uses a liveness-probe misconfiguration.

## What it does

The API has an opt-in `/leak` endpoint. When `LEAK_ENABLED=true`, each request keeps 512 KiB in memory and never
releases it. With the container's 128 MiB limit, memory climbs steadily until Kubernetes kills the container with
`OOMKilled`. It does not crash outright, which makes it a realistic slow leak.

| | |
|---|---|
| Trigger | Repeated requests to `/leak` with `LEAK_ENABLED=true` |
| Signal | Container memory rising in Grafana, then `OOMKilled` and a restart |
| Root cause | The application holds references to every allocation |
| Fix | Release or bound the cached data; alert on memory growth before the limit |

The endpoint returns 404 unless `LEAK_ENABLED=true`. Observed results are in
[docs/incident-reports/02-memory-oom.md](docs/incident-reports/02-memory-oom.md).
