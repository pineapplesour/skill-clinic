#!/usr/bin/env python3
"""Provision the cheap LLM judge that Skill Clinic uses, on the Nosana GPU network.

Flow (all real Nosana API calls, credit-based, no wallet needed):
  1. take an official Nosana template job definition (Ollama server + model),
  2. pin it to IPFS (Nosana's community Pinata key, intentionally public in nosana-kit),
  3. POST /jobs/list  -> job address + run account, paid with account credits,
  4. poll until /api/tags (Ollama) or /v1/models (vLLM) answers 200,
  5. print the OpenAI-compatible base URL to export as LLM_BASE_URL.

Usage:
  set -a; source .env; set +a
  .venv/bin/python nosana_deploy.py --template qwen3-5-9b --market nvidia-3090 --wait
  .venv/bin/python nosana_deploy.py --status <job-address>
  .venv/bin/python nosana_deploy.py --stop <job-address>

IPFS pinning uses NOSANA_PINATA_JWT when set; otherwise the public, rate-limited
nosana-kit default below (so the script keeps working with no extra setup).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid

import requests

API = "https://api.nosana.com/api"
NODE_URL = "https://{job}.node.k8s.prd.nos.ci"
# Scoped, rate-limited Pinata key shipped as the default in nosana-kit/packages/ipfs/src/defaults.
# Intentionally public upstream; override it with NOSANA_PINATA_JWT to use your own key.
DEFAULT_PUBLIC_PINATA_JWT = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VySW5mb3JtYXRpb24iOnsiaWQiOiJmZDUwODE1NS1jZDJhLTRlMzYtYWI4MC0wNmMxNjRmZWY1MTkiLCJlbWFpbCI6Implc3NlQG5vc2FuYS5pbyIsImVtYWlsX3ZlcmlmaWVkIjp0cnVlLCJwaW5fcG9saWN5Ijp7InJlZ2lvbnMiOlt7ImlkIjoiRlJBMSIsImRlc2lyZWRSZXBsaWNhdGlvbkNvdW50IjoxfV0sInZlcnNpb24iOjF9LCJtZmFfZW5hYmxlZCI6ZmFsc2UsInN0YXR1cyI6IkFDVElWRSJ9LCJhdXRoZW50aWNhdGlvblR5cGUiOiJzY29wZWRLZXkiLCJzY29wZWRLZXlLZXkiOiI1YzVhNWM2N2RlYWU2YzNhNzEwOCIsInNjb3BlZEtleVNlY3JldCI6ImYxOWFjZDUyZDk4ZTczNjU5MmEyY2IzZjQwYWUxNGE2ZmYyYTkxNDJjZTRiN2EzZGQ5OTYyOTliMmJkN2IzYzEiLCJpYXQiOjE2ODY3NzE5Nzl9.r4_pWCCT79Jis6L3eegjdBdAt5MpVd1ymDkBuNE25g8"
)


def pinata_jwt() -> str:
    """Your own Pinata JWT if NOSANA_PINATA_JWT is set, else the public default."""
    return os.environ.get("NOSANA_PINATA_JWT") or DEFAULT_PUBLIC_PINATA_JWT


def _headers() -> dict:
    key = os.environ.get("NOSANA_API_KEY")
    if not key:
        sys.exit("NOSANA_API_KEY is not set (put it in .env and `set -a; source .env; set +a`)")
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def _get_json(url: str, what: str) -> dict | list:
    """GET and decode, or exit with a readable message instead of a traceback."""
    try:
        r = requests.get(url, headers=_headers(), timeout=30)
    except requests.RequestException as err:
        sys.exit(f"{what}: could not reach {url} ({type(err).__name__}: {err})")
    if not r.ok:
        sys.exit(f"{what} failed {r.status_code}: {r.text[:400]}")
    try:
        return r.json()
    except ValueError:
        sys.exit(f"{what}: response was not JSON: {r.text[:200]}")


def markets() -> list[dict]:
    return _get_json(f"{API}/markets", "GET /markets")


def market_address(slug_or_address: str) -> str:
    if len(slug_or_address) > 30:
        return slug_or_address
    listing = markets()
    if not isinstance(listing, list):
        sys.exit(f"GET /markets: expected a list of markets, got {type(listing).__name__}")
    for m in listing:
        if isinstance(m, dict) and m.get("slug") == slug_or_address:
            address = m.get("address")
            if not address:
                sys.exit(f"market '{slug_or_address}' has no address field")
            return address
    known = ", ".join(sorted(str(m.get("slug")) for m in listing if isinstance(m, dict)))[:300]
    sys.exit(f"unknown market slug: {slug_or_address}\n  known slugs: {known}")


def template_job_definition(template_id: str) -> dict:
    t = _get_json(f"{API}/templates/{template_id}", f"GET /templates/{template_id}")
    if not isinstance(t, dict) or "jobDefinition" not in t:
        sys.exit(f"template '{template_id}' has no jobDefinition (unknown template id?)")
    jd = t["jobDefinition"]
    jd.setdefault("meta", {})["trigger"] = "api"
    return jd


def pin_to_ipfs(job_definition: dict) -> str:
    try:
        r = requests.post(
            "https://api.pinata.cloud/pinning/pinJSONToIPFS",
            headers={"Authorization": f"Bearer {pinata_jwt()}", "content-type": "application/json"},
            json=job_definition,
            timeout=60,
        )
    except requests.RequestException as err:
        sys.exit(f"IPFS pin: could not reach Pinata ({type(err).__name__}: {err})")
    if not r.ok:
        sys.exit(f"IPFS pin failed {r.status_code}: {r.text[:400]}\n"
                 "  The built-in public nosana-kit key is rate-limited; "
                 "set NOSANA_PINATA_JWT to your own Pinata JWT.")
    try:
        data = r.json()
    except ValueError:
        sys.exit(f"IPFS pin: response was not JSON: {r.text[:200]}")
    ipfs_hash = data.get("IpfsHash") if isinstance(data, dict) else None
    if not ipfs_hash:
        sys.exit(f"IPFS pin: no IpfsHash in the Pinata response: {str(data)[:200]}")
    return ipfs_hash


def post_job(ipfs_hash: str, market: str, timeout_s: int = 3600) -> dict:
    try:
        r = requests.post(
            f"{API}/jobs/list",
            headers={**_headers(), "Idempotency-Key": str(uuid.uuid4())},
            json={"ipfsHash": ipfs_hash, "market": market, "timeout": timeout_s},
            timeout=90,
        )
    except requests.RequestException as err:
        sys.exit(f"POST /jobs/list: could not reach {API} ({type(err).__name__}: {err})")
    if not r.ok:
        sys.exit(f"jobs/list failed {r.status_code}: {r.text[:400]}")
    try:
        data = r.json()
    except ValueError:
        sys.exit(f"POST /jobs/list: response was not JSON: {r.text[:200]}")
    if not isinstance(data, dict) or not data.get("job"):
        sys.exit(f"POST /jobs/list: no job address in the response: {str(data)[:300]}")
    return data


def job_status(job: str) -> dict:
    return _get_json(f"{API}/jobs/{job}", f"GET /jobs/{job}")


#: Health paths of the two server kinds we deploy: Ollama and vLLM (OpenAI-compatible).
READY_PATHS = ("/api/tags", "/v1/models")


def ready_path(job: str) -> str | None:
    """The first health path that answers 200, or None if neither does."""
    base = NODE_URL.format(job=job)
    for path in READY_PATHS:
        try:
            if requests.get(base + path, timeout=8).status_code == 200:
                return path
        except requests.RequestException:
            continue
    return None


def endpoint_ready(job: str) -> bool:
    """True when either the Ollama (/api/tags) or the vLLM (/v1/models) API answers 200."""
    return ready_path(job) is not None


def wait_ready(job: str, max_minutes: int = 20) -> bool:
    t0 = time.time()
    while time.time() - t0 < max_minutes * 60:
        st = job_status(job)
        print(f"  [{int(time.time()-t0):4d}s] state={st.get('state')} node={str(st.get('node',''))[:8]}", flush=True)
        path = ready_path(job)
        if path:
            kind = "ollama" if path == "/api/tags" else "vllm"
            print(f"  endpoint answered 200 on {path} ({kind})", flush=True)
            return True
        time.sleep(10)
    return False


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--template", default="qwen3-5-9b", help="Nosana template id (Ollama LLM templates: qwen3-5-9b, gemma3-4b, gpt-oss-20b ...)")
    ap.add_argument("--market", default="nvidia-3090", help="GPU market slug or address")
    ap.add_argument("--timeout", type=int, default=3600, help="job lifetime in seconds")
    ap.add_argument("--wait", action="store_true", help="block until the endpoint answers")
    ap.add_argument("--status", metavar="JOB", help="print job status and exit")
    ap.add_argument("--stop", metavar="JOB", help="stop a running job and exit")
    a = ap.parse_args()

    if a.status:
        print(json.dumps(job_status(a.status), indent=1)[:2000])
        print("endpoint ready:", endpoint_ready(a.status))
        return
    if a.stop:
        r = requests.post(f"{API}/jobs/{a.stop}/stop", headers=_headers(), timeout=60)
        print(r.status_code, r.text[:300])
        return

    jd = template_job_definition(a.template)
    model = jd.get("global", {}).get("variables", {}).get("MODEL", "?")
    market = market_address(a.market)
    print(f"template={a.template} model={model} market={a.market} ({market})")
    h = pin_to_ipfs(jd)
    print("ipfs:", h)
    res = post_job(h, market, a.timeout)
    job = res["job"]
    print("job:", job, "run:", res.get("run"), "credits:", res.get("credits"))
    base = NODE_URL.format(job=job)
    print("endpoint:", base)
    if a.wait:
        ok = wait_ready(job)
        print("READY" if ok else "NOT READY (still pulling the model?)")
    print("\nexport LLM_BASE_URL=" + base + "/v1")
    print("export LLM_MODEL=" + model)
    print("export LLM_API_KEY=x")


if __name__ == "__main__":
    main()
