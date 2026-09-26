"""Check .env credentials without printing secrets or raw provider errors."""

import argparse
import ipaddress
import json
import os
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from dotenv import load_dotenv
from openai import OpenAI
from pymongo import MongoClient


def failure(service, exc):
    # Provider messages, response bodies, and Mongo topology errors can contain
    # credentials or connection strings. Only emit fixed classifications.
    message = str(exc).lower()
    code = getattr(exc, "code", None)
    reasons = {
        "invalid_api_key", "insufficient_quota", "model_not_found",
        "unsupported_parameter", "unsupported_value",
    }
    reason = code if isinstance(code, str) and code in reasons else "request_failed"
    if service == "MongoDB":
        if code == 18 or "authentication failed" in message:
            reason = "authentication_rejected"
        elif code == 13:
            reason = "database_permission_denied"
        elif any(term in message for term in ("nxdomain", "resolution", "resolve", "dns")):
            reason = "dns_failure"
        elif "ssl" in message or "tls" in message:
            reason = "tls_failure"
        elif "timed out" in message or "timeout" in message:
            reason = "connection_timeout_check_atlas_ip_access_list_and_network"
    status = getattr(exc, "status_code", None)
    return {
        "service": service,
        "ok": False,
        "reason": reason,
        "http_status": status if isinstance(status, int) else None,
    }


def check_openai(inference=False):
    if not os.environ.get("OPENAI_API_KEY"):
        return {"service": "OpenAI", "ok": False, "reason": "not_configured"}
    try:
        with OpenAI(timeout=20, max_retries=0) as client:
            model = client.models.retrieve(os.environ.get("OPENAI_MODEL", "gpt-6-astra"))
            if inference:
                response = client.responses.create(
                    model=model.id, input="Reply with OK.", reasoning={"effort": "low"},
                    max_output_tokens=32, store=False,
                )
                if response.status != "completed":
                    return {"service": "OpenAI", "ok": False, "reason": "inference_not_completed"}
        return {"service": "OpenAI", "ok": True, "check": "inference" if inference else "model_access"}
    except Exception as exc:
        return failure("OpenAI", exc)


def check_mongodb():
    if not os.environ.get("MONGODB_URI"):
        return {"service": "MongoDB", "ok": False, "reason": "not_configured"}
    try:
        with MongoClient(
            os.environ["MONGODB_URI"], serverSelectionTimeoutMS=12000,
            connectTimeoutMS=5000, socketTimeoutMS=10000,
        ) as client:
            client.admin.command("ping")
            client[os.environ.get("MONGODB_DATABASE", "da_vinci")].list_collection_names()
        return {"service": "MongoDB", "ok": True, "check": "ping_and_database_read_access"}
    except Exception as exc:
        return failure("MongoDB", exc)


def check_public_ip():
    try:
        with urllib.request.urlopen("https://api.ipify.org", timeout=10) as response:
            address = ipaddress.ip_address(response.read(128).decode().strip())
        return {"service": "Network", "ok": True, "public_egress_ip": str(address)}
    except Exception as exc:
        return failure("Network", exc)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inference", action="store_true", help="Make one small, billable model request")
    parser.add_argument("--public-ip", action="store_true", help="Display HTTPS egress IP using api.ipify.org")
    args = parser.parse_args()
    # Explicitly test the edited file, even when the shell has older values.
    load_dotenv(".env", override=True)
    checks = [lambda: check_openai(args.inference), check_mongodb]
    if args.public_ip:
        checks.append(check_public_ip)
    with ThreadPoolExecutor(max_workers=len(checks)) as pool:
        results = list(pool.map(lambda check: check(), checks))
    for result in results:
        print(json.dumps(result), flush=True)
    return 0 if all(result["ok"] for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
