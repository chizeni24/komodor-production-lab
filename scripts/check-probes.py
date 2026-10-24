#!/usr/bin/env python3
"""Probe standard: liveness must not depend on downstream dependencies.

The follow-up control after the incident. PyYAML is needed only for this development check.
"""
import argparse
from pathlib import Path
import sys
import yaml


def validate(path):
    resources = list(yaml.safe_load_all(Path(path).read_text()))
    api = next(d for d in resources if d and d.get("kind") == "Deployment" and d["metadata"]["name"] == "kaop-api")
    c = next(c for c in api["spec"]["template"]["spec"]["containers"] if c["name"] == "api")
    assert c["livenessProbe"]["httpGet"]["path"] == "/healthz", "Liveness must use dependency-independent /healthz"
    assert c["readinessProbe"]["httpGet"]["path"] == "/readyz", "Readiness must use /readyz"


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("manifest", nargs="?", default="k8s/api.yaml")
    try:
        validate(p.parse_args().manifest)
    except (AssertionError, KeyError, StopIteration) as error:
        print("FAIL:", error, file=sys.stderr)
        sys.exit(1)
    print("PASS: readiness and liveness are correctly separated")
