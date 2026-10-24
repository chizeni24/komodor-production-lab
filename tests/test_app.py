import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("app", ROOT / "app.py")
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)


def request(path):
    handler = object.__new__(app.Handler)
    handler.path = path
    responses = []
    handler.respond = lambda status, text: responses.append((status, text))
    handler.do_GET()
    return responses[0]


class AppTests(unittest.TestCase):
    def test_redis_outage_fails_readiness_but_not_liveness(self):
        with patch.object(app, "check_redis", side_effect=ConnectionRefusedError), patch.object(app.logging, "exception"):
            self.assertEqual(request("/healthz")[0], 200)
            self.assertEqual(request("/readyz")[0], 503)
            self.assertEqual(request("/")[0], 503)

    def test_readiness_reports_real_dependency_result(self):
        with patch.object(app, "check_redis", return_value="PONG"):
            self.assertEqual(request("/readyz"), (200, "API connected to Redis: PONG"))

    def test_service_link_env_cannot_break_startup(self):
        import os
        with patch.dict(os.environ, {"REDIS_PORT": "tcp://10.96.0.1:6379"}):
            fresh = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(fresh)
        self.assertEqual(fresh.REDIS_PORT, 6379)

    def test_unknown_path(self):
        self.assertEqual(request("/leak")[0], 404)

    def test_redis_timeout_is_shorter_than_probe_timeout(self):
        import yaml
        docs = list(yaml.safe_load_all((ROOT / "k8s/api.yaml").read_text()))
        api = next(d for d in docs if d["kind"] == "Deployment")
        c = api["spec"]["template"]["spec"]["containers"][0]
        self.assertLess(app.REDIS_TIMEOUT_SECONDS, c["readinessProbe"]["timeoutSeconds"])


if __name__ == "__main__":
    unittest.main()
