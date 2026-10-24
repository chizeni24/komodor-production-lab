import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location("grafana_lab", ROOT / "scripts/grafana_lab.py")
grafana = importlib.util.module_from_spec(spec)
spec.loader.exec_module(grafana)

CURRENT_RULE = {"uid": grafana.RULE_UID, "title": "KAOP Lab - API Container Restarts", "for": "1m", "labels": None,
                "annotations": {"summary": "old"}, "noDataState": "NoData", "execErrState": "Error",
                "data": [{"refId": "A", "model": {"expr": "sum(old)"}}, {"refId": "C", "model": {"expression": "A"}}]}


class FakeOpener:
    def __init__(self):
        self.requests = []
        self.policy = {"receiver": "empty", "group_by": ["grafana_folder", "alertname"]}
        self.contacts = []

    def open(self, request, timeout):
        body = json.loads(request.data) if request.data else None
        self.requests.append((request.get_method(), request.full_url, body, dict(request.header_items())))
        path = request.full_url[len(grafana.URL):].split("?")[0]
        if path == "/api/v1/provisioning/alert-rules/" + grafana.RULE_UID:
            value = CURRENT_RULE
        elif path == "/api/v1/provisioning/policies":
            if request.get_method() == "PUT":
                self.policy = body
            value = self.policy
        elif path.startswith("/api/v1/provisioning/contact-points"):
            if request.get_method() == "POST":
                self.contacts.append({**body, "uid": "cp1"})
            value = self.contacts
        elif path == "/api/prometheus/grafana/api/v1/rules":
            value = {"data": {"groups": [{"rules": [{"uid": grafana.RULE_UID, "state": "firing", "health": "ok", "alerts": []}]}]}}
        else:
            value = {}
        return io.BytesIO(json.dumps(value).encode())


class GrafanaTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.files = {}
        for name, value in {"token": "UNIT_TEST_TOKEN", "url": "https://kaop.example.invalid/hook", "secret": "ENDPOINT_SECRET"}.items():
            path = Path(self.tmp.name) / name
            path.write_text(value)
            os.chmod(path, 0o600)
            self.files[name] = str(path)

    def test_desired_rule_adds_identity_and_keeps_threshold(self):
        spec = json.loads(grafana.RULE_FILE.read_text())
        rule = grafana.desired_rule(CURRENT_RULE, spec)
        self.assertEqual(rule["labels"]["deployment"], "kaop-api")
        self.assertEqual(rule["labels"]["kaop"], "incident")
        self.assertIn("by (cluster, namespace, pod, container)", rule["data"][0]["model"]["expr"])
        self.assertEqual(rule["data"][1], CURRENT_RULE["data"][1])
        self.assertEqual(rule["noDataState"], "OK")
        self.assertEqual(CURRENT_RULE["data"][0]["model"]["expr"], "sum(old)")
        # The alert must describe the symptom, not hint at the answer.
        text = json.dumps(spec["annotations"]).lower()
        for hint in ("probe", "liveness", "readyz", "redis"):
            self.assertNotIn(hint, text)

    def test_connect_creates_contact_point_and_route_without_leaking_secrets(self):
        opener = FakeOpener()
        original = grafana.Client.__init__
        grafana.Client.__init__ = lambda self, token, opener_=None: original(self, token, opener)
        try:
            with contextlib.redirect_stdout(io.StringIO()) as out:
                grafana.main(["connect-kaop", "--token-file", self.files["token"],
                              "--endpoint-url-file", self.files["url"], "--endpoint-token-file", self.files["secret"]])
        finally:
            grafana.Client.__init__ = original
        self.assertEqual(opener.contacts[0]["settings"]["authorization_credentials"], "ENDPOINT_SECRET")
        route = grafana.find_route(opener.policy)
        self.assertEqual(route["receiver"], grafana.CONTACT_POINT)
        self.assertEqual(opener.policy["receiver"], "empty")
        self.assertNotIn("ENDPOINT_SECRET", out.getvalue())
        self.assertNotIn("UNIT_TEST_TOKEN", out.getvalue())
        self.assertTrue(all(url.startswith(grafana.URL + "/api/") for _, url, _, _ in opener.requests))

    def test_route_is_idempotent(self):
        policy = {"receiver": "empty", "routes": [{"receiver": "x", "object_matchers": [grafana.ROUTE_MATCHER]}, {"receiver": "other"}]}
        self.assertEqual(grafana.find_route(policy)["receiver"], "x")

    def test_rule_state_and_private_token_file(self):
        state = grafana.rule_state(None, grafana.Client("t", FakeOpener()))
        self.assertEqual(state["state"], "Alerting")
        os.chmod(self.files["token"], 0o644)
        with self.assertRaises(grafana.GrafanaError):
            grafana.load_token(self.files["token"])

    def test_redirects_refused(self):
        self.assertIsNone(grafana.NoRedirect().redirect_request(None, None, 302, "", {}, "https://elsewhere.invalid"))


if __name__ == "__main__":
    unittest.main()
