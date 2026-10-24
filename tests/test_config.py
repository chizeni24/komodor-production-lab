import copy
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


guard = load("check_probes", "scripts/check-probes.py")
sync = load("sync_configmap", "scripts/sync-configmap.py")


class ConfigTests(unittest.TestCase):
    def test_configmap_and_checksum_match_app(self):
        self.assertEqual(sync.main(check_only=True), 0)
        cm = yaml.safe_load((ROOT / "k8s/api-configmap.yaml").read_text())
        self.assertEqual(cm["data"]["app.py"], (ROOT / "app.py").read_text())

    def test_every_object_stays_in_lab_namespace(self):
        for path in sorted((ROOT / "k8s").glob("*.yaml")):
            for doc in yaml.safe_load_all(path.read_text()):
                if doc["kind"] == "Namespace":
                    self.assertEqual(doc["metadata"]["name"], "kaop-demo")
                else:
                    self.assertEqual(doc["metadata"]["namespace"], "kaop-demo", path.name)
                self.assertIn(doc["kind"], {"Namespace", "ConfigMap", "Deployment", "Service"})

    def test_probe_standard_rejects_dependency_coupled_liveness(self):
        docs = list(yaml.safe_load_all((ROOT / "k8s/api.yaml").read_text()))
        bad = copy.deepcopy(docs)
        api = next(d for d in bad if d["kind"] == "Deployment")
        api["spec"]["template"]["spec"]["containers"][0]["livenessProbe"]["httpGet"]["path"] = "/readyz"
        with tempfile.TemporaryDirectory() as temp:
            good_path, bad_path = Path(temp) / "good.yaml", Path(temp) / "bad.yaml"
            good = copy.deepcopy(docs)
            next(d for d in good if d["kind"] == "Deployment")["spec"]["template"]["spec"]["containers"][0]["livenessProbe"]["httpGet"]["path"] = "/healthz"
            good_path.write_text(yaml.safe_dump_all(good))
            bad_path.write_text(yaml.safe_dump_all(bad))
            guard.validate(good_path)
            with self.assertRaises(AssertionError):
                guard.validate(bad_path)
            result = subprocess.run(["python3", "-B", str(ROOT / "scripts/check-probes.py"), str(bad_path)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)


if __name__ == "__main__":
    unittest.main()
