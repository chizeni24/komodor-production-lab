#!/usr/bin/env python3
"""Grafana Cloud setup for the KAOP lab. Token values are read from files and never printed.

  status        read-only: restart alert state, labels, and whether alerts route to KAOP
  apply-rule    make the restart alert carry workload identity (monitoring/alert-rule.json)
  connect-kaop  create the KAOP webhook contact point and route the lab alert to it
  test-kaop     send Grafana's test notification to the KAOP contact point
  apply-dashboard  create or update the "KAOP Lab" dashboard (monitoring/dashboard.json)

apply-rule, connect-kaop and test-kaop need an Editor service-account token
(default ~/.config/komodor-secrets/grafana-editor-token). status works with a Viewer token.
"""
import argparse
import copy
import datetime as dt
import json
from pathlib import Path
import sys
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
URL = "https://azurepopcorn464.grafana.net"
RULE_UID = "cg254gvwpyjggf"
RULE_FILE = ROOT / "monitoring/alert-rule.json"
DASHBOARD_FILE = ROOT / "monitoring/dashboard.json"
FOLDER_UID = "fhs2vc"
SECRETS = Path.home() / ".config/komodor-secrets"
READ_TOKEN = SECRETS / "grafana-sa-token"
EDITOR_TOKEN = SECRETS / "grafana-editor-token"
CONTACT_POINT = "kaop-incident-endpoint"
ROUTE_MATCHER = ["kaop", "=", "incident"]


class GrafanaError(Exception):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # never forward the Authorization header to another host


def load_token(path):
    path = Path(path).expanduser()
    if not path.is_file():
        raise GrafanaError("token file not found: " + str(path))
    if path.stat().st_mode & 0o077:
        raise GrafanaError("token file must be private (chmod 600): " + str(path))
    token = path.read_text().strip()
    if not token:
        raise GrafanaError("token file is empty: " + str(path))
    return token


def read_secret(path, label):
    try:
        return load_token(path)
    except GrafanaError as error:
        raise GrafanaError(label + ": " + str(error)) from None


class Client:
    def __init__(self, token, opener=None):
        self.token = token
        self.opener = opener or urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def request(self, method, path, body=None, params=None):
        url = URL + path + ("?" + urllib.parse.urlencode(params) if params else "")
        data = json.dumps(body).encode() if body is not None else None
        headers = {"Authorization": "Bearer " + self.token, "Accept": "application/json"}
        if data is not None:
            headers.update({"Content-Type": "application/json", "X-Disable-Provenance": "true"})
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with self.opener.open(req, timeout=20) as response:
                raw = response.read()
                return json.loads(raw) if raw.strip() else {}
        except urllib.error.HTTPError as error:
            hint = {401: "token rejected", 403: "token lacks permission (Editor needed for changes)", 404: "not found"}.get(error.code, "")
            raise GrafanaError(method + " " + path + " returned HTTP " + str(error.code) + (" (" + hint + ")" if hint else "")) from None
        except (urllib.error.URLError, TimeoutError) as error:
            raise GrafanaError("cannot reach Grafana: " + str(getattr(error, "reason", error))) from None


def rule_state(token, client=None):
    client = client or Client(token)
    rules = client.request("GET", "/api/prometheus/grafana/api/v1/rules")
    for group in rules.get("data", {}).get("groups", []):
        for rule in group.get("rules", []):
            if rule.get("uid") == RULE_UID or rule.get("grafana_alert", {}).get("uid") == RULE_UID:
                state = {"inactive": "Normal", "pending": "Pending", "firing": "Alerting"}.get(rule.get("state"), str(rule.get("state")))
                return {"state": state, "health": rule.get("health"),
                        "instances": [{k: a.get("labels", {}).get(k) for k in ("pod", "deployment", "namespace")} | {"state": a.get("state")}
                                      for a in rule.get("alerts", [])]}
    raise GrafanaError("restart alert " + RULE_UID + " not found")


def desired_rule(current, spec):
    rule = copy.deepcopy(current)
    for query in rule["data"]:
        if query["refId"] == "A":
            query["model"]["expr"] = spec["query"]
    rule.update({k: spec[k] for k in ("title", "for", "labels", "annotations", "noDataState", "execErrState")})
    return rule


def find_route(policy):
    for route in policy.get("routes") or []:
        if ROUTE_MATCHER in (route.get("object_matchers") or []):
            return route
    return None


def cmd_status(args):
    client = Client(read_secret(args.token_file, "status token"))
    state = rule_state(None, client)
    rule = client.request("GET", "/api/v1/provisioning/alert-rules/" + RULE_UID)
    policy = client.request("GET", "/api/v1/provisioning/policies")
    route = find_route(policy)
    contact = [c for c in client.request("GET", "/api/v1/provisioning/contact-points") if c.get("name") == CONTACT_POINT]
    labels = rule.get("labels") or {}
    print("Restart alert   %s (health %s)" % (state["state"], state["health"]))
    for instance in state["instances"]:
        print("  instance      %s" % json.dumps(instance))
    print("Workload labels %s" % ("yes: " + ", ".join(f"{k}={v}" for k, v in sorted(labels.items())) if labels.get("deployment") else "MISSING (run apply-rule)"))
    print("KAOP contact    %s" % ("configured" if contact else "not configured (run connect-kaop on access day)"))
    print("KAOP route      %s" % (("kaop=incident -> " + route.get("receiver")) if route else "not configured"))
    return 0


def cmd_apply_rule(args):
    client = Client(read_secret(args.token_file, "editor token"))
    spec = json.loads(RULE_FILE.read_text())
    current = client.request("GET", "/api/v1/provisioning/alert-rules/" + RULE_UID)
    backup = ROOT / "artifacts/grafana" / ("rule-before-" + dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + ".json")
    backup.parent.mkdir(parents=True, exist_ok=True)
    backup.write_text(json.dumps(current, indent=2) + "\n")
    updated = desired_rule(current, spec)
    if args.dry_run:
        print(json.dumps({k: updated[k] for k in ("title", "for", "labels", "annotations")}, indent=2))
        print("Query A: " + spec["query"])
        return 0
    client.request("PUT", "/api/v1/provisioning/alert-rules/" + RULE_UID, updated)
    print("Updated restart alert: workload labels, neutral annotations, per-pod series. Backup: " + str(backup.relative_to(ROOT)))
    return 0


def kaop_route():
    return {"receiver": CONTACT_POINT, "object_matchers": [ROUTE_MATCHER],
            "group_by": ["alertname", "namespace", "deployment"],
            "group_wait": "10s", "group_interval": "1m", "repeat_interval": "4h", "continue": False}


def cmd_connect(args):
    client = Client(read_secret(args.token_file, "editor token"))
    if args.dry_run:
        policy = client.request("GET", "/api/v1/provisioning/policies")
        planned = dict(policy, routes=[r for r in (policy.get("routes") or []) if ROUTE_MATCHER not in (r.get("object_matchers") or [])] + [kaop_route()])
        print("Current policy:\n" + json.dumps(policy, indent=2))
        print("Planned policy (root receiver and grouping unchanged):\n" + json.dumps(planned, indent=2))
        print("Planned contact point: name=%s type=webhook POST <KAOP endpoint URL> Authorization: Bearer <KAOP token>" % CONTACT_POINT)
        return 0
    url = read_secret(args.endpoint_url_file, "KAOP endpoint URL")
    if not url.startswith("https://"):
        raise GrafanaError("KAOP endpoint URL must start with https://")
    settings = {"url": url, "httpMethod": "POST"}
    if args.auth == "bearer":
        settings.update(authorization_scheme="Bearer",
                        authorization_credentials=read_secret(args.endpoint_token_file, "KAOP endpoint token"))
    contact = {"name": CONTACT_POINT, "type": "webhook", "settings": settings, "disableResolveMessage": False}
    existing = [c for c in client.request("GET", "/api/v1/provisioning/contact-points") if c.get("name") == CONTACT_POINT]
    if existing:
        client.request("PUT", "/api/v1/provisioning/contact-points/" + existing[0]["uid"], {**contact, "uid": existing[0]["uid"]})
    else:
        client.request("POST", "/api/v1/provisioning/contact-points", contact)
    policy = client.request("GET", "/api/v1/provisioning/policies")
    route = kaop_route()
    policy["routes"] = [r for r in (policy.get("routes") or []) if ROUTE_MATCHER not in (r.get("object_matchers") or [])] + [route]
    client.request("PUT", "/api/v1/provisioning/policies", policy)
    print("Contact point '%s' %s; alerts labelled kaop=incident now route to KAOP (group_wait 10s)." % (CONTACT_POINT, "updated" if existing else "created"))
    print("Next: python3 scripts/grafana_lab.py test-kaop, then check Integrations -> Endpoints in KAOP")
    return 0


def cmd_test(args):
    client = Client(read_secret(args.token_file, "editor token"))
    contact = [c for c in client.request("GET", "/api/v1/provisioning/contact-points") if c.get("name") == CONTACT_POINT]
    if not contact:
        raise GrafanaError("contact point not configured; run connect-kaop first")
    body = {"receivers": [{"name": CONTACT_POINT, "grafana_managed_receiver_configs": [
        {"uid": contact[0]["uid"], "name": CONTACT_POINT, "type": "webhook", "settings": contact[0]["settings"]}]}],
        "alert": {"labels": {"alertname": "KAOP connectivity test", "kaop": "incident", "namespace": "kaop-demo",
                             "deployment": "kaop-api", "kind": "Deployment"},
                  "annotations": {"summary": "Connectivity test from Grafana; not an incident"}}}
    result = client.request("POST", "/api/alertmanager/grafana/config/api/v1/receivers/test", body)
    statuses = [c.get("status") for r in result.get("receivers", []) for c in r.get("grafana_managed_receiver_configs", [])]
    print("Grafana test notification: " + (", ".join(map(str, statuses)) or "sent"))
    return 0 if all(s == "ok" for s in statuses) else 1


def cmd_dashboard(args):
    client = Client(read_secret(args.token_file, "editor token"))
    dashboard = json.loads(DASHBOARD_FILE.read_text())
    dashboard.pop("id", None)
    result = client.request("POST", "/api/dashboards/db", {"dashboard": dashboard, "folderUid": FOLDER_UID, "overwrite": True,
                                                            "message": "Applied from monitoring/dashboard.json"})
    print("Dashboard %s: %s%s (version %s)" % (result.get("status"), URL, result.get("url"), result.get("version")))
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)
    s = sub.add_parser("status")
    s.add_argument("--token-file", default=str(READ_TOKEN))
    a = sub.add_parser("apply-rule")
    a.add_argument("--token-file", default=str(EDITOR_TOKEN))
    a.add_argument("--dry-run", action="store_true")
    c = sub.add_parser("connect-kaop")
    c.add_argument("--token-file", default=str(EDITOR_TOKEN))
    c.add_argument("--endpoint-url-file", default=str(SECRETS / "kaop-endpoint-url"))
    c.add_argument("--endpoint-token-file", default=str(SECRETS / "kaop-endpoint-token"))
    c.add_argument("--auth", choices=["bearer", "none"], default="bearer",
                   help="bearer: send the endpoint token as Authorization: Bearer; none: the URL already carries it")
    c.add_argument("--dry-run", action="store_true", help="show the planned contact point and policy; change nothing")
    t = sub.add_parser("test-kaop")
    t.add_argument("--token-file", default=str(EDITOR_TOKEN))
    d = sub.add_parser("apply-dashboard")
    d.add_argument("--token-file", default=str(EDITOR_TOKEN))
    args = p.parse_args(argv)
    return {"status": cmd_status, "apply-rule": cmd_apply_rule, "connect-kaop": cmd_connect, "test-kaop": cmd_test,
            "apply-dashboard": cmd_dashboard}[args.command](args)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except GrafanaError as error:
        print("FAIL: " + str(error), file=sys.stderr)
        sys.exit(1)
