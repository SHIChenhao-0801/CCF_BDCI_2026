"""Start the frozen proxy; normalized LF source hash supports Git archive exports."""

import argparse
from decimal import Decimal
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import sys


PROXY_PATH = Path(__file__).resolve().parent.parent / "jiuwenswarm/scripts/deepseek_budget_proxy.py"
PROXY_SHA256 = "c09644e0de84e208cfc866da2f446e142b8d6a87eed0170033e011b63ba5baec"
if sha256(PROXY_PATH.read_text(encoding="utf-8").encode("utf-8")).hexdigest() != PROXY_SHA256:
    raise ValueError("proxy source differs from the reviewed final freeze")
spec = importlib.util.spec_from_file_location("_ccf_full_context_proxy", PROXY_PATH)
proxy = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = proxy
spec.loader.exec_module(proxy)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--request-policy", type=Path)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=19080)
    args = parser.parse_args()
    ledger_path = args.ledger.expanduser().resolve()
    state = json.loads(ledger_path.read_text(encoding="utf-8"))
    if state["active_reservations"]:
        raise ValueError("stop the old proxy and wait for all reservations to settle first")
    env = proxy._read_env_file(args.env_file.expanduser().resolve())
    policy = proxy.BudgetPolicy(
        model=env.get("DEEPSEEK_MODEL", "deepseek-flash"),
        budget_cny=Decimal(state["policy"]["budget_cny"]),
        input_cny_per_million=Decimal("2"),
        output_cny_per_million=Decimal("8"),
        max_input_tokens=1_048_576,
        max_output_tokens=32_768,
    )
    ledger = proxy.BudgetLedger(ledger_path, policy)
    try:
        settings = proxy.ProxySettings(
            upstream_base_url=env.get("DEEPSEEK_API_BASE", "https://api.deepseek.com"),
            api_key=env.get("DEEPSEEK_API_KEY", ""),
        )
        proxy.uvicorn.run(
            proxy.create_app(settings, ledger, request_policy=args.request_policy),
            host=proxy.validate_loopback_host(args.host),
            port=args.port,
            log_level="warning",
        )
    finally:
        ledger.close()


if __name__ == "__main__":
    main()
