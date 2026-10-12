"""Reproduce report ablations without changing production code or supplied tapes."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gameday_lab.client import ResilientClient
from gameday_lab.factory import build_client
from gameday_lab.sim.config import load_config
from gameday_lab.sim.engine import evaluate_checks, run_scenario


class UnfilteredClient(ResilientClient):
    """Deliberately unsafe experiment only: quantify missing capability filtering."""

    def ladder(self, task: str) -> list[str]:
        return list(self.order)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=25)
    parser.add_argument("--out", default="reports/experiments.json")
    args = parser.parse_args()
    cfg = load_config()
    cache_cfg = load_config(scenarios_path="configs/scenarios_cache.yaml")
    results = {}

    def run(label, config, scenario, name="resilient", unfiltered=False):
        client = (UnfilteredClient(config.provider_infos(), config.fallback_order, config.client, config.seed)
                  if unfiltered else build_client(name, config))
        metrics = run_scenario(config, scenario, client, args.seed).metrics()
        checks = evaluate_checks(metrics, config.scenarios[scenario].checks)
        results[label] = {"metrics": metrics, "checks": checks, "pass": all(checks.values())}
        print(label, "PASS" if all(checks.values()) else "FAIL (ablation may intentionally fail)")

    for scenario in ("G2_overload_storm", "G3_brownout"):
        run(f"normal_{scenario}", cfg, scenario)
        settings = {**cfg.client, "max_attempts_per_provider": 5,
                    "breaker": {**cfg.client["breaker"], "min_calls": 1000000000}}
        run(f"broken_breaker_budget_on_{scenario}", replace(cfg, client=settings), scenario)
        disabled = {**settings, "retry_budget_ratio": 100, "retry_budget_max_tokens": 1e9,
                    "retry_budget_min_per_s": 1e6}
        run(f"broken_breaker_budget_off_{scenario}", replace(cfg, client=disabled), scenario)
    for scenario in ("G4_slow_region", "G6_provider_outage"):
        run(f"timeout_5_{scenario}", cfg, scenario)
        run(f"timeout_30_{scenario}", replace(cfg, client={**cfg.client, "attempt_timeout_s": 30}), scenario)
    run("unfiltered_G6", cfg, "G6_provider_outage", unfiltered=True)
    variants = {
        "final": {},
        "starter": {"similarity_threshold": 0.8, "ttl_s": 600, "max_stale_s": 0},
        "threshold_0.8": {"similarity_threshold": 0.8},
        "threshold_0.97": {"similarity_threshold": 0.97},
        "ttl_60": {"ttl_s": 60},
        "ttl_300": {"ttl_s": 300},
        "no_stale": {"max_stale_s": 0},
    }
    run("cache_disabled", cache_cfg, "C1_faq_outage")
    for label, overrides in variants.items():
        run(f"cache_{label}", replace(cache_cfg, cache={**cache_cfg.cache, **overrides}),
            "C1_faq_outage", name="cached")
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"seed": args.seed, "client": cfg.client, "cache": cache_cfg.cache,
                               "results": results}, indent=2), encoding="utf-8")
    print("Wrote", out)


if __name__ == "__main__":
    main()
