#!/usr/bin/env python3
"""Operator CLI for the KAOP lab. Standard library only; never reads Secrets.

  preflight  read-only health check of the lab (cluster, pods, endpoints, HTTP, code consistency)
  deploy     apply k8s/ manifests exactly as they exist at a git ref (main, a PR branch, a SHA)
  outage     take Redis down for a bounded window, watch what the API does, then restore Redis
             and measure how long the API takes to come back
  evidence   capture a read-only, sanitized snapshot of the namespace
  reset      break-glass: bring Redis back and wait for the API; does not change the API spec
"""
import argparse
import contextlib
import datetime as dt
import fcntl
import hashlib
import json
from pathlib import Path
import re
import selectors
import shutil
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import grafana_lab  # noqa: E402

ARTIFACTS = ROOT / "artifacts"
INCIDENTS = ARTIFACTS / "incidents"
STATE = ARTIFACTS / "demo-state"
CONTEXT = "kind-kaop-demo"
NAMESPACE = "kaop-demo"
NODE = "kaop-demo-control-plane"
MANIFESTS = ["k8s/namespace.yaml", "k8s/api-configmap.yaml", "k8s/redis.yaml", "k8s/api.yaml"]
ALLOWED_KINDS = {"Namespace", "ConfigMap", "Deployment", "Service"}
API_RECOVERY_TIMEOUT = 420  # CrashLoopBackOff can delay a restart by up to five minutes


class DemoError(Exception):
    pass


def utc(epoch=None):
    moment = dt.datetime.fromtimestamp(epoch, dt.timezone.utc) if epoch else dt.datetime.now(dt.timezone.utc)
    return moment.isoformat(timespec="seconds")


def rel(path):
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def run_id():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:6]


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.replace(path)


def redact(text):
    text = re.sub(r"(?i)(bearer\s+)[^\s\"']+", r"\1[REDACTED]", text)
    text = re.sub(r"(?i)((?:password|token|api[_-]?key|authorization|credential|secret)\s*[=:]\s*)[^\s,;]+", r"\1[REDACTED]", text)
    text = re.sub(r"\b(?:gh[pousr]_[A-Za-z0-9_]+|glc_[A-Za-z0-9_=+-]+|glsa_[A-Za-z0-9_]+)\b", "[REDACTED]", text)
    return text


def sanitized(value):
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, list):
        return [sanitized(x) for x in value]
    if isinstance(value, dict):
        return {k: sanitized(v) for k, v in value.items()}
    return value


def container(deployment, name="api"):
    return next(c for c in deployment["spec"]["template"]["spec"]["containers"] if c["name"] == name)


def probe_path(deployment, probe):
    return container(deployment).get(probe, {}).get("httpGet", {}).get("path")


def pod_record(p):
    return {
        "name": p["metadata"]["name"], "uid": p["metadata"]["uid"],
        "deletionTimestamp": p["metadata"].get("deletionTimestamp"),
        "phase": p.get("status", {}).get("phase"),
        "conditions": p.get("status", {}).get("conditions", []),
        "containers": [{k: c.get(k) for k in ("name", "ready", "restartCount", "state", "lastState", "imageID")}
                       for c in p.get("status", {}).get("containerStatuses", [])],
    }


def deployment_record(d):
    return {
        "name": d["metadata"]["name"], "uid": d["metadata"]["uid"],
        "generation": d["metadata"]["generation"], "replicas": d["spec"].get("replicas"),
        "readyReplicas": d.get("status", {}).get("readyReplicas", 0),
        "annotations": {k: v for k, v in d["spec"]["template"]["metadata"].get("annotations", {}).items() if k.startswith("kaop-demo/")},
        "containers": [{**{k: c.get(k) for k in ("name", "image", "command", "livenessProbe", "readinessProbe", "resources")},
                        "env": [{"name": e["name"], "value": e.get("value") if e["name"].startswith("REDIS_") else "[REDACTED]"}
                                for e in c.get("env", [])]}
                       for c in d["spec"]["template"]["spec"]["containers"]],
    }


def api_pods(pods):
    return [p for p in pods if p["metadata"].get("labels", {}).get("app") == "kaop-api" and not p["metadata"].get("deletionTimestamp")]


def pod_state(p):
    statuses = [c for c in p.get("status", {}).get("containerStatuses", []) if c["name"] == "api"]
    if not statuses:
        return "Pending"
    state = statuses[0].get("state", {})
    if "waiting" in state:
        return state["waiting"].get("reason", "Waiting")
    if "terminated" in state:
        return state["terminated"].get("reason", "Terminated")
    return "Ready" if statuses[0].get("ready") else "Running/NotReady"


class Kube:
    def __init__(self, kubeconfig, context):
        if context != CONTEXT:
            raise DemoError("Refusing unexpected context; required: " + CONTEXT)
        self.kubeconfig = str(Path(kubeconfig).expanduser().resolve())
        if not Path(self.kubeconfig).is_file():
            raise DemoError("Lab kubeconfig missing: " + self.kubeconfig)
        self.base = ["kubectl", "--kubeconfig=" + self.kubeconfig, "--context=" + context, "--request-timeout=15s"]

    def call(self, *args, json_result=False, timeout=30, stdin=None):
        try:
            r = subprocess.run(self.base + list(args), capture_output=True, text=True, timeout=timeout, input=stdin)
        except subprocess.TimeoutExpired:
            raise DemoError("kubectl timed out: " + " ".join(args[:3])) from None
        if r.returncode:
            # kubectl stderr is summarized, not echoed: exec-credential plugins may print secrets.
            first = redact(r.stderr.strip().splitlines()[0]) if r.stderr.strip() else ""
            raise DemoError("kubectl failed: " + " ".join(args[:3]) + (" | " + first[:200] if first else ""))
        return json.loads(r.stdout) if json_result else r.stdout

    def get(self, resource, name=None, namespace=NAMESPACE, selector=None):
        args = ["get", resource] + ([name] if name else [])
        if namespace:
            args += ["-n", namespace]
        if selector:
            args += ["-l", selector]
        return self.call(*args, "-o", "json", json_result=True)

    def guard(self):
        nodes = self.get("nodes", namespace=None)["items"]
        if len(nodes) != 1 or nodes[0]["metadata"]["name"] != NODE:
            raise DemoError("Refusing cluster: expected the single-node kind cluster " + NODE)
        return nodes

    def http_checks(self):
        p = subprocess.Popen(self.base + ["-n", NAMESPACE, "port-forward", "--address=127.0.0.1", "service/kaop-api", ":80"],
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        try:
            selector = selectors.DefaultSelector()
            selector.register(p.stdout, selectors.EVENT_READ)
            deadline, port = time.monotonic() + 12, None
            while time.monotonic() < deadline and p.poll() is None:
                if selector.select(timeout=0.2):
                    match = re.search(r"Forwarding from 127\.0\.0\.1:(\d+)", p.stdout.readline())
                    if match:
                        port = match.group(1)
                        break
            selector.close()
            if port is None:
                raise DemoError("Could not open a loopback port-forward to service/kaop-api")
            result = {}
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            for path, expected in [("/healthz", 200), ("/readyz", 200), ("/", 200), ("/missing", 404)]:
                try:
                    response = opener.open("http://127.0.0.1:" + port + path, timeout=5)
                except urllib.error.HTTPError as error:
                    response = error
                with response:
                    body = response.read(2048).decode(errors="replace")
                    result[path] = {"status": response.code, "pong": "PONG" in body}
                    if response.code != expected or (path in ("/", "/readyz") and "PONG" not in body):
                        raise DemoError("HTTP check failed at " + path + ": " + str(response.code))
            return result
        finally:
            p.terminate()
            try:
                p.wait(timeout=3)
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait(timeout=3)
            p.stdout.close()


def require_ready(deployment):
    s = deployment.get("status", {})
    if deployment["spec"].get("replicas") != 1 or s.get("readyReplicas") != 1 or s.get("updatedReplicas") != 1:
        raise DemoError(deployment["metadata"]["name"] + " must have exactly one Ready, updated replica")
    if s.get("observedGeneration", 0) < deployment["metadata"]["generation"]:
        raise DemoError(deployment["metadata"]["name"] + " rollout not yet observed")


def git(*args):
    return subprocess.check_output(["git", "-C", str(ROOT)] + list(args), text=True)


def describe_probes(api):
    live, ready = probe_path(api, "livenessProbe"), probe_path(api, "readinessProbe")
    if live == ready:
        return "LATENT DEFECT: liveness and readiness both probe " + str(live) + " (liveness depends on Redis)"
    return "Probes decoupled: liveness " + str(live) + ", readiness " + str(ready)


def preflight(kube, quiet=False):
    if (STATE / "active.json").exists():
        raise DemoError("An outage marker exists (artifacts/demo-state/active.json); run reset first")
    nodes = kube.guard()
    for node in nodes:
        conditions = {c["type"]: c["status"] for c in node["status"]["conditions"]}
        if conditions.get("Ready") != "True" or any(conditions.get(x) == "True" for x in ("MemoryPressure", "DiskPressure", "PIDPressure")):
            raise DemoError("Node is not Ready or reports resource pressure")
    api, redis = kube.get("deployment", "kaop-api"), kube.get("deployment", "redis")
    require_ready(api)
    require_ready(redis)
    code = kube.get("configmap", "kaop-api-code")["data"]["app.py"]
    stamped = api["spec"]["template"]["metadata"].get("annotations", {}).get("kaop-demo/code-checksum")
    if stamped != hashlib.sha256(code.encode()).hexdigest()[:16]:
        raise DemoError("Running code checksum does not match the ConfigMap; redeploy with: demo.sh deploy --ref <ref>")
    pods = kube.get("pods")["items"]
    for label in ("kaop-api", "redis"):
        selected = [p for p in pods if p["metadata"].get("labels", {}).get("app") == label and not p["metadata"].get("deletionTimestamp")]
        statuses = selected[0].get("status", {}).get("containerStatuses", []) if len(selected) == 1 else []
        if not statuses or not all(c.get("ready") for c in statuses):
            raise DemoError(label + " needs exactly one Ready pod")
    slices = kube.get("endpointslices")["items"]
    for service in ("kaop-api", "redis"):
        if not any(s["metadata"].get("labels", {}).get("kubernetes.io/service-name") == service
                   and any(e.get("conditions", {}).get("ready") is True for e in s.get("endpoints") or []) for s in slices):
            raise DemoError(service + " has no Ready endpoint")
    report = {"captured_at": utc(), "git_head": git("rev-parse", "HEAD").strip(),
              "code_checksum": stamped, "probes": describe_probes(api),
              "deployments": [deployment_record(api), deployment_record(redis)],
              "api_restarts": sum(c.get("restartCount", 0) for p in api_pods(pods) for c in p.get("status", {}).get("containerStatuses", [])),
              "http": kube.http_checks()}
    if not quiet:
        print("PASS  cluster, pods, endpoints, code checksum, /healthz, /readyz and Redis PONG")
        print("INFO  " + report["probes"])
    return report


def render_ref(ref):
    try:
        sha = git("rev-parse", "--verify", ref + "^{commit}").strip()
    except subprocess.CalledProcessError:
        raise DemoError("Unknown git ref: " + ref + " (run git fetch?)") from None
    return sha, "\n---\n".join(git("show", sha + ":" + path) for path in MANIFESTS)


def validate_objects(kube, manifest):
    rendered = kube.call("apply", "--dry-run=client", "-o", "json", "-f", "-", json_result=True, stdin=manifest)
    items = rendered.get("items", [rendered])
    for item in items:
        kind, meta = item.get("kind"), item.get("metadata", {})
        if kind not in ALLOWED_KINDS:
            raise DemoError("Refusing to apply kind " + str(kind))
        if kind == "Namespace" and meta.get("name") != NAMESPACE:
            raise DemoError("Refusing to create namespace " + str(meta.get("name")))
        if kind != "Namespace" and meta.get("namespace") != NAMESPACE:
            raise DemoError("Refusing object outside " + NAMESPACE + ": " + kind + "/" + str(meta.get("name")))
    return items


def subset(want, have):
    """True when every field in `want` is present in `have` with the same value (server defaults ignored)."""
    if isinstance(want, dict):
        return isinstance(have, dict) and all(subset(v, have.get(k)) for k, v in want.items())
    return want == have


def drift(kube, desired):
    """Compare the fields this lab cares about between git and the live Deployments."""
    problems = []
    for item in desired:
        if item["kind"] != "Deployment":
            continue
        live = kube.get("deployment", item["metadata"]["name"])
        want_c = item["spec"]["template"]["spec"]["containers"][0]
        have_c = live["spec"]["template"]["spec"]["containers"][0]
        for field in ("image", "command", "livenessProbe", "readinessProbe"):
            if field in want_c and not subset(want_c[field], have_c.get(field)):
                problems.append(item["metadata"]["name"] + "." + field)
        if not subset(item["spec"]["template"]["metadata"].get("annotations", {}), live["spec"]["template"]["metadata"].get("annotations", {})):
            problems.append(item["metadata"]["name"] + ".annotations")
        if sorted(e["name"] for e in have_c.get("env", [])) != sorted(e["name"] for e in want_c.get("env", [])):
            problems.append(item["metadata"]["name"] + ".env")
        if live["spec"].get("replicas") != item["spec"].get("replicas", 1):
            problems.append(item["metadata"]["name"] + ".replicas")
    return problems


def deploy(kube, ref):
    kube.guard()
    sha, manifest = render_ref(ref)
    desired = validate_objects(kube, manifest)
    print("Applying k8s/ from " + ref + " @ " + sha[:12] + " (" + str(len(desired)) + " objects)", flush=True)
    kube.call("apply", "-f", "-", stdin=manifest, timeout=60)
    for name in ("redis", "kaop-api"):
        kube.call("rollout", "status", "deployment/" + name, "-n", NAMESPACE, "--timeout=180s", timeout=190)
    problems = drift(kube, desired)
    if problems:
        raise DemoError("Live state still differs from git after apply: " + ", ".join(problems))
    report = preflight(kube)
    report.update(deployed_ref=ref, deployed_sha=sha)
    save(ARTIFACTS / "deploys" / (run_id() + ".json"), report)
    print("PASS  deployed " + ref + " @ " + sha[:12])
    return report


@contextlib.contextmanager
def mutation_lock():
    STATE.mkdir(parents=True, exist_ok=True)
    with (STATE / "mutation.lock").open("a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise DemoError("Another lab mutation is running; Ctrl-C it in its own terminal first") from None
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def evidence(kube, directory=None, quiet=False):
    directory = directory or INCIDENTS / run_id()
    directory.mkdir(parents=True, exist_ok=True)
    report = {"captured_at": utc(), "context": CONTEXT, "namespace": NAMESPACE, "errors": []}
    collectors = [
        ("deployments", lambda: [deployment_record(kube.get("deployment", n)) for n in ("kaop-api", "redis")]),
        ("replicasets", lambda: [{"name": r["metadata"]["name"], "created": r["metadata"]["creationTimestamp"],
                                  "revision": r["metadata"].get("annotations", {}).get("deployment.kubernetes.io/revision"),
                                  "replicas": r["spec"].get("replicas"),
                                  "liveness": (r["spec"]["template"]["spec"]["containers"][0].get("livenessProbe") or {}).get("httpGet", {}).get("path")}
                                 for r in kube.get("replicasets", selector="app=kaop-api")["items"]]),
        ("pods", lambda: [pod_record(p) for p in kube.get("pods")["items"] if p["metadata"].get("labels", {}).get("app") in ("kaop-api", "redis")]),
        ("events", lambda: [{k: e.get(k) for k in ("type", "reason", "message", "firstTimestamp", "lastTimestamp", "eventTime", "count", "involvedObject", "series")}
                            for e in kube.get("events")["items"] if e.get("involvedObject", {}).get("name", "").startswith(("kaop-api", "redis"))]),
        ("endpointslices", lambda: [{"name": s["metadata"]["name"], "endpoints": s.get("endpoints"), "ports": s.get("ports")}
                                    for s in kube.get("endpointslices")["items"]
                                    if s["metadata"].get("labels", {}).get("kubernetes.io/service-name") in ("kaop-api", "redis")]),
    ]
    for name, collect in collectors:
        try:
            save(directory / (name + ".json"), sanitized(collect()))
        except (DemoError, KeyError, IndexError) as error:
            report["errors"].append(name + ": " + str(error))
    try:
        for p in api_pods(kube.get("pods")["items"]):
            for previous in (False, True):
                try:
                    args = ["logs", "-n", NAMESPACE, p["metadata"]["name"], "-c", "api", "--timestamps", "--since=30m", "--tail=300"]
                    logs = kube.call(*(args + (["--previous"] if previous else [])))
                    (directory / (p["metadata"]["name"] + ("-previous" if previous else "-current") + ".log")).write_text(redact(logs))
                except DemoError:
                    report["errors"].append("logs unavailable: " + p["metadata"]["name"] + (" previous" if previous else " current"))
    except DemoError as error:
        report["errors"].append(str(error))
    report["git_head"] = git("rev-parse", "HEAD").strip()
    save(directory / "summary.json", report)
    if not quiet:
        print("Evidence:", rel(directory))
    return directory


def incident_signals(pods, events, initial, started_epoch):
    delta, states = 0, []
    for p in pods:
        uid = p["metadata"]["uid"]
        if uid in initial:
            count = sum(c.get("restartCount", 0) for c in p.get("status", {}).get("containerStatuses", []) if c["name"] == "api")
            delta += max(0, count - initial[uid])
            states.append(pod_state(p))
    seen = {"liveness_503": False, "readiness_503": False}
    for e in events:
        stamp = (e.get("series") or {}).get("lastObservedTime") or e.get("lastTimestamp") or e.get("eventTime") or e.get("metadata", {}).get("creationTimestamp")
        try:
            recent = dt.datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp() >= started_epoch
        except (AttributeError, ValueError):
            recent = False
        if e.get("involvedObject", {}).get("uid") in initial and recent and "503" in e.get("message", ""):
            if "Liveness probe failed" in e["message"]:
                seen["liveness_503"] = True
            if "Readiness probe failed" in e["message"]:
                seen["readiness_503"] = True
    return {"api_restart_delta": delta, "fresh_liveness_http_503": seen["liveness_503"],
            "fresh_readiness_http_503": seen["readiness_503"], "api_state": ",".join(states) or "none"}


def check_alert_normal(args):
    if args.skip_grafana_check:
        print("WARN  Grafana alert state not checked (--skip-grafana-check)")
        return None
    try:
        state = grafana_lab.rule_state(grafana_lab.load_token(args.grafana_token_file))
    except grafana_lab.GrafanaError as error:
        print("WARN  Grafana alert state unavailable (" + str(error) + "); continuing", flush=True)
        return None
    if state["state"] != "Normal":
        raise DemoError("Restart alert is " + state["state"] + "; wait for Normal so KAOP gets a fresh notification "
                        "(or pass --skip-grafana-check)")
    print("PASS  Grafana restart alert is Normal", flush=True)
    return state


def wait_api_ready(kube, timeout):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        pods = api_pods(kube.get("pods")["items"])
        if len(pods) == 1 and pod_state(pods[0]) == "Ready":
            return time.time()
        time.sleep(2)
    return None


def outage(kube, args):
    baseline = preflight(kube)
    check_alert_normal(args)
    rid = run_id()
    folder = INCIDENTS / rid
    save(folder / "baseline.json", baseline)
    pods = api_pods(kube.get("pods")["items"])
    initial = {p["metadata"]["uid"]: sum(c.get("restartCount", 0) for c in p.get("status", {}).get("containerStatuses", []) if c["name"] == "api")
               for p in pods}
    record = {"run_id": rid, "started_at": utc(), "max_seconds": args.max_seconds, "probes": baseline["probes"],
              "api_pod": pods[0]["metadata"]["name"] if pods else None}
    save(STATE / "active.json", record)
    first_signal, signals, scaled, interrupted, restored_by = None, {}, False, False, "script"
    def interrupt(signum, frame):
        raise KeyboardInterrupt

    old = {s: signal.signal(s, interrupt) for s in (signal.SIGINT, signal.SIGTERM)}
    try:
        print("Run " + rid + "  " + record["probes"], flush=True)
        print("Redis outage for up to " + str(args.max_seconds) + "s. It ends when someone scales Redis back up "
              "(the action KAOP proposes) or on Ctrl-C.", flush=True)
        outage_epoch = time.time()
        record["outage_started_at"] = utc(outage_epoch)
        scaled = True
        kube.call("scale", "deployment/redis", "-n", NAMESPACE, "--replicas=0")
        deadline, last_print, last_capture = time.monotonic() + args.max_seconds, None, 0
        while time.monotonic() < deadline:
            signals = incident_signals(kube.get("pods")["items"], kube.get("events")["items"], initial, outage_epoch)
            elapsed = int(time.time() - outage_epoch)
            line = "restarts=+{api_restart_delta} liveness503={fresh_liveness_http_503} readiness503={fresh_readiness_http_503} api={api_state}".format(**signals)
            if line != last_print or elapsed % 30 < 5:
                print("T+%03ds  %s" % (elapsed, line), flush=True)
                last_print = line
            if signals["api_restart_delta"] and first_signal is None:
                first_signal = {**signals, "seconds_after_outage": elapsed, "at": utc()}
                save(folder / "first-restart.json", first_signal)
            if signals["api_restart_delta"] and time.monotonic() - last_capture >= 60:
                evidence(kube, folder / "during", quiet=True)
                last_capture = time.monotonic()
            save(folder / "signals.json", signals)
            if kube.get("deployment", "redis")["spec"].get("replicas", 0) >= 1:
                restored_by = "operator"
                print("T+%03ds  Redis was scaled back up by an operator: ending the outage" % elapsed, flush=True)
                break
            time.sleep(min(5, max(0, deadline - time.monotonic())))
        else:
            print("Maximum outage window reached", flush=True)
    except KeyboardInterrupt:
        interrupted = True
        print("\nCtrl-C: ending the outage", flush=True)
    finally:
        for s in old:
            signal.signal(s, signal.SIG_IGN)
        try:
            if scaled:
                evidence(kube, folder / "before-restore", quiet=True)
                kube.call("scale", "deployment/redis", "-n", NAMESPACE, "--replicas=1")
                kube.call("rollout", "status", "deployment/redis", "-n", NAMESPACE, "--timeout=120s", timeout=130)
                redis_ready = time.time()
                print("Redis is back at " + utc(redis_ready) + "; waiting for the API to become Ready...", flush=True)
                api_ready = wait_api_ready(kube, API_RECOVERY_TIMEOUT)
                record.update(outage_ended_at=utc(redis_ready), interrupted=interrupted, restored_by=restored_by, signals=signals,
                              first_restart=first_signal, api_ready_at=utc(api_ready) if api_ready else None,
                              api_recovery_lag_seconds=round(api_ready - redis_ready, 1) if api_ready else None)
                save(folder / "result.json", record)
                if api_ready is None:
                    raise DemoError("API not Ready " + str(API_RECOVERY_TIMEOUT) + "s after Redis returned; marker kept, run reset")
                (STATE / "active.json").unlink(missing_ok=True)
            else:
                (STATE / "active.json").unlink(missing_ok=True)
        finally:
            for s, handler in old.items():
                signal.signal(s, handler)
    print("\nRESULT  restarts=+%s  liveness503=%s  API Ready %ss after Redis returned  evidence=%s" % (
        signals.get("api_restart_delta"), signals.get("fresh_liveness_http_503"),
        record["api_recovery_lag_seconds"], rel(folder)))
    if not signals.get("api_restart_delta"):
        print("        No liveness restarts: liveness is decoupled from Redis, so the API recovered as soon as Redis did.")
    return record


def reset(kube):
    kube.guard()
    redis = kube.get("deployment", "redis")
    if redis["spec"].get("replicas") != 1:
        kube.call("scale", "deployment/redis", "-n", NAMESPACE, "--replicas=1")
    kube.call("rollout", "status", "deployment/redis", "-n", NAMESPACE, "--timeout=120s", timeout=130)
    if wait_api_ready(kube, API_RECOVERY_TIMEOUT) is None:
        raise DemoError("API did not become Ready; inspect with: demo.sh evidence")
    (STATE / "active.json").unlink(missing_ok=True)
    report = preflight(kube)
    print("PASS  reset complete (Redis restored; API spec unchanged; use deploy to change it)")
    return report


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", choices=["preflight", "deploy", "outage", "evidence", "reset"])
    p.add_argument("--ref", help="deploy: git ref whose k8s/ manifests to apply, e.g. origin/main")
    p.add_argument("--kubeconfig", default=str(Path.home() / ".kube/kaop-demo-rootful.yaml"))
    p.add_argument("--context", default=CONTEXT)
    p.add_argument("--approve-live-mutation", action="store_true", help="required for deploy, outage and reset")
    p.add_argument("--max-seconds", type=int, default=600, help="outage: upper bound, 60..1800; Ctrl-C ends it sooner")
    p.add_argument("--grafana-token-file", default=str(grafana_lab.READ_TOKEN))
    p.add_argument("--skip-grafana-check", action="store_true", help="outage: do not require the restart alert to be Normal")
    p.add_argument("--report", help="preflight/reset: also write the report to this path")
    args = p.parse_args(argv)
    if args.command in ("deploy", "outage", "reset") and not args.approve_live_mutation:
        raise DemoError(args.command + " changes the cluster: add --approve-live-mutation")
    if args.command == "deploy" and not args.ref:
        raise DemoError("deploy needs --ref, e.g. --ref origin/main")
    if not 60 <= args.max_seconds <= 1800:
        raise DemoError("--max-seconds must be between 60 and 1800")
    if not shutil.which("kubectl") or not shutil.which("git"):
        raise DemoError("Required binaries: kubectl and git")
    kube = Kube(args.kubeconfig, args.context)
    if args.command == "preflight":
        report = preflight(kube)
    elif args.command == "evidence":
        kube.guard()
        evidence(kube)
        return
    else:
        with mutation_lock():
            report = {"deploy": lambda: deploy(kube, args.ref), "outage": lambda: outage(kube, args), "reset": lambda: reset(kube)}[args.command]()
    if args.report:
        save(Path(args.report), report)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Interrupted", file=sys.stderr)
        sys.exit(130)
    except (DemoError, OSError, ValueError, KeyError, StopIteration, subprocess.CalledProcessError) as error:
        print("FAIL: " + str(error), file=sys.stderr)
        sys.exit(1)
