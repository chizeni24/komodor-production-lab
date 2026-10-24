# Incident 02: Gradual Memory Leak

## Environment
- Kubernetes: kind
- Workload: Python API with Redis dependency
- Container memory limit: 128 MiB
- Leak size: 512 KiB per request

## Trigger
An opt-in /leak endpoint retained allocated memory
across successive HTTP requests.

## Observations
- Grafana showed progressively increasing memory.
- Initial controlled test: 40 requests.
- Extended test: 187 successful additional requests.
- Request 188: connection closed unexpectedly.
- Kubernetes termination reason: OOMKilled.
- Affected container restart count: 1.

## Root cause
The application deliberately retained references to
allocated bytearrays, resulting in unbounded memory
growth under sustained request traffic.

## Recovery
- Disabled LEAK_ENABLED.
- Rolled out a replacement API pod.
- Verified the replacement was Ready with zero restarts.

## Prevention
- Remove unbounded retention.
- Bound caches and in-memory collections.
- Monitor memory growth trends.
- Alert on memory pressure before OOM termination.

## Status
Reproduced and recovered successfully.
KAOP investigation not yet performed.
