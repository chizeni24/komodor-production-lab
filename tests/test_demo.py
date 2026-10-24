import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location("demo", ROOT / "scripts/demo.py")
demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(demo)

CODE = "print('hi')\n"
CHECKSUM = hashlib.sha256(CODE.encode()).hexdigest()[:16]


def deployment(name, liveness="/healthz"):
    probes = {"livenessProbe": {"httpGet": {"path": liveness, "port": 8080, "scheme": "HTTP"}, "timeoutSeconds": 3},
              "readinessProbe": {"httpGet": {"path": "/readyz", "port": 8080, "scheme": "HTTP"}, "timeoutSeconds": 3}} if name == "kaop-api" else {}
    return {"metadata": {"name": name, "uid": name, "generation": 1},
            "spec": {"replicas": 1, "template": {"metadata": {"annotations": {"kaop-demo/code-checksum": CHECKSUM} if name == "kaop-api" else {}},
                                                 "spec": {"containers": [{"name": "api" if name == "kaop-api" else "redis", "image": "img",
                                                                          "env": [{"name": "REDIS_HOST", "value": "redis"}], **probes}]}}},
            "status": {"readyReplicas": 1, "updatedReplicas": 1, "observedGeneration": 1}}


class FakeKube:
    def __init__(self, liveness="/healthz"):
        self.deployments = {"kaop-api": deployment("kaop-api", liveness), "redis": deployment("redis")}
        self.writes = []
        self.restarts = 0
        self.events = []

    def guard(self):
        return [{"status": {"conditions": [{"type": "Ready", "status": "True"}]}}]

    def get(self, resource, name=None, namespace=None, selector=None):
        if resource == "deployment":
            return copy.deepcopy(self.deployments[name])
        if resource == "configmap":
            return {"data": {"app.py": CODE}}
        if resource == "pods":
            api_ready = self.deployments["redis"]["spec"]["replicas"] == 1
            return {"items": [
                {"metadata": {"name": "kaop-api-x", "uid": "api-uid", "labels": {"app": "kaop-api"}},
                 "status": {"containerStatuses": [{"name": "api", "ready": api_ready, "restartCount": self.restarts,
                                                   "state": {"running": {}} if api_ready else {"waiting": {"reason": "CrashLoopBackOff"}}}]}},
                {"metadata": {"name": "redis-x", "uid": "redis-uid", "labels": {"app": "redis"}},
                 "status": {"containerStatuses": [{"name": "redis", "ready": True, "restartCount": 0, "state": {"running": {}}}]}}]}
        if resource == "endpointslices":
            return {"items": [{"metadata": {"name": n, "labels": {"kubernetes.io/service-name": n}}, "endpoints": [{"conditions": {"ready": True}}]}
                              for n in self.deployments]}
        if resource == "events":
            return {"items": self.events}
        if resource == "replicasets":
            return {"items": []}
        raise AssertionError(resource)

    def http_checks(self):
        return {"/": {"status": 200, "pong": True}}

    def call(self, *args, **kwargs):
        if args[0] == "scale":
            self.writes.append(args)
            self.deployments["redis"]["spec"]["replicas"] = int(args[-1].split("=")[1])
            if self.deployments["redis"]["spec"]["replicas"] == 0:
                self.restarts += 2
                self.events.append({"involvedObject": {"uid": "api-uid"}, "lastTimestamp": demo.utc(time.time() + 1),
                                    "message": "Liveness probe failed: HTTP probe failed with statuscode: 503"})
            return ""
        if args[0] in ("rollout", "logs"):
            return ""
        raise AssertionError(args)


class Args:
    max_seconds = 60
    skip_grafana_check = True
    grafana_token_file = "/nonexistent"


class DemoTests(unittest.TestCase):
    def setUp(self):
        self.out = patch("sys.stdout", new_callable=io.StringIO)
        self.out.start()
        self.addCleanup(self.out.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        for name, value in {"STATE": "state", "INCIDENTS": "incidents", "ARTIFACTS": "artifacts"}.items():
            p = patch.object(demo, name, Path(self.tmp.name) / value)
            p.start()
            self.addCleanup(p.stop)
        sleeper = patch.object(demo.time, "sleep")
        sleeper.start()
        self.addCleanup(sleeper.stop)

    def test_mutations_require_explicit_approval(self):
        for command in (["deploy", "--ref", "HEAD"], ["outage"], ["reset"]):
            r = subprocess.run(["bash", str(ROOT / "scripts/demo.sh")] + command, capture_output=True, text=True)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("--approve-live-mutation", r.stderr)

    def test_wrong_context_rejected(self):
        with self.assertRaises(demo.DemoError):
            demo.Kube("/nonexistent", "production")

    def test_preflight_is_read_only_and_reports_latent_defect(self):
        k = FakeKube(liveness="/readyz")
        report = demo.preflight(k)
        self.assertEqual(k.writes, [])
        self.assertIn("LATENT DEFECT", report["probes"])
        self.assertIn("decoupled", demo.preflight(FakeKube())["probes"])

    def test_preflight_rejects_stale_code(self):
        k = FakeKube()
        k.deployments["kaop-api"]["spec"]["template"]["metadata"]["annotations"]["kaop-demo/code-checksum"] = "stale"
        with self.assertRaises(demo.DemoError):
            demo.preflight(k)

    def test_mutation_lock_refuses_overlap(self):
        with demo.mutation_lock():
            with self.assertRaises(demo.DemoError):
                with demo.mutation_lock():
                    self.fail("overlap permitted")

    def test_outage_restores_redis_and_measures_recovery(self):
        k = FakeKube(liveness="/readyz")
        with patch.object(demo, "evidence"), patch.object(demo.time, "monotonic", side_effect=[0, 0, 0, 61, 61, 61, 61]):
            record = demo.outage(k, Args())
        self.assertEqual([w[-1] for w in k.writes], ["--replicas=0", "--replicas=1"])
        self.assertEqual(record["signals"]["api_restart_delta"], 2)
        self.assertTrue(record["signals"]["fresh_liveness_http_503"])
        self.assertIsNotNone(record["api_recovery_lag_seconds"])
        self.assertFalse((demo.STATE / "active.json").exists())
        self.assertEqual(demo.probe_path(k.deployments["kaop-api"], "livenessProbe"), "/readyz")  # API spec untouched

    def test_outage_interrupt_still_restores_redis(self):
        k = FakeKube()
        original = k.get
        def get(resource, *a, **kw):
            if resource == "events" and k.deployments["redis"]["spec"]["replicas"] == 0:
                raise KeyboardInterrupt
            return original(resource, *a, **kw)
        with patch.object(k, "get", side_effect=get), patch.object(demo, "evidence"):
            record = demo.outage(k, Args())
        self.assertTrue(record["interrupted"])
        self.assertEqual(k.deployments["redis"]["spec"]["replicas"], 1)

    def test_outage_refuses_while_alert_firing(self):
        k = FakeKube()
        class Firing(Args):
            skip_grafana_check = False
        with patch.object(demo.grafana_lab, "load_token", return_value="t"), \
                patch.object(demo.grafana_lab, "rule_state", return_value={"state": "Alerting"}):
            with self.assertRaises(demo.DemoError):
                demo.outage(k, Firing())
        self.assertEqual(k.writes, [])
        self.assertFalse((demo.STATE / "active.json").exists())

    def test_old_events_and_replaced_pods_not_counted(self):
        pods = FakeKube().get("pods")["items"]
        pods[0]["status"]["containerStatuses"][0]["restartCount"] = 2
        event = {"involvedObject": {"uid": "api-uid"}, "lastTimestamp": "2020-01-01T00:00:00Z", "message": "Liveness probe failed: HTTP probe failed with statuscode: 503"}
        s = demo.incident_signals(pods, [event], {"api-uid": 0}, time.time() - 30)
        self.assertEqual(s["api_restart_delta"], 2)
        self.assertFalse(s["fresh_liveness_http_503"])
        pods[0]["metadata"]["uid"] = "replacement"
        self.assertEqual(demo.incident_signals(pods, [], {"api-uid": 0}, time.time())["api_restart_delta"], 0)

    def test_drift_ignores_server_defaults_but_catches_probe_change(self):
        k = FakeKube()
        desired = copy.deepcopy(k.deployments["kaop-api"])
        desired["kind"] = "Deployment"
        for probe in ("livenessProbe", "readinessProbe"):
            desired["spec"]["template"]["spec"]["containers"][0][probe]["httpGet"].pop("scheme")
        self.assertEqual(demo.drift(k, [desired]), [])
        desired["spec"]["template"]["spec"]["containers"][0]["livenessProbe"]["httpGet"]["path"] = "/readyz"
        self.assertEqual(demo.drift(k, [desired]), ["kaop-api.livenessProbe"])

    def test_deploy_refuses_objects_outside_lab(self):
        k = FakeKube()
        def call(*args, **kwargs):
            return {"items": [{"kind": "ClusterRole", "metadata": {"name": "x"}}]}
        with patch.object(k, "call", side_effect=call):
            with self.assertRaises(demo.DemoError):
                demo.validate_objects(k, "irrelevant")

    def test_redaction(self):
        result = demo.redact("Authorization=Bearer abc123 token=abc password=foo ghp_ABCdef123 glsa_XYZ")
        for value in ("abc123", "token=abc", "password=foo", "ghp_ABC", "glsa_XYZ"):
            self.assertNotIn(value, result)
        self.assertEqual(json.loads(json.dumps(demo.sanitized({"m": "token=abc"})))["m"], "token=[REDACTED]")


if __name__ == "__main__":
    unittest.main()
