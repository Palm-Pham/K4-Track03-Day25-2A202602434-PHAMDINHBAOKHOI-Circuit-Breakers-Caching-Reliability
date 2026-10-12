"""Validate A-C tapes across seeds, optionally shifting all incident windows.

Run: python scripts/validate_abc.py --seeds 25,26,27 --shift-s 17
Only in-memory copies of scenarios are changed; the supplied tapes stay intact.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gameday_lab.factory import build_client
from gameday_lab.sim.config import load_config
from gameday_lab.sim.engine import evaluate_checks, run_scenario


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", default="25,26,27")
    parser.add_argument("--shift-s", type=float, default=0)
    parser.add_argument("--out", default="reports/abc_validation.json")
    args = parser.parse_args()
    cfg = load_config()
    variants = [("public", cfg)]
    if args.shift_s:
        shift = args.shift_s
        scenarios = {}
        for key, scenario in cfg.scenarios.items():
            windows = {
                field: tuple(replace(w, start=w.start + shift, end=w.end + shift)
                             for w in getattr(scenario, field))
                for field in ("effects", "traffic", "malformed", "primary_only")
            }
            scenarios[key] = replace(
                scenario, **windows, duration_s=scenario.duration_s + shift,
                restore_at=None if scenario.restore_at is None else scenario.restore_at + shift,
            )
        variants.append(("shifted", replace(cfg, scenarios=scenarios)))
    runs = []
    for variant, config in variants:
        for seed in map(int, args.seeds.split(",")):
            for key, scenario in config.scenarios.items():
                metrics = run_scenario(config, key, build_client("resilient", config), seed).metrics()
                checks = evaluate_checks(metrics, scenario.checks)
                passed = all(checks.values())
                runs.append({"variant": variant, "seed": seed, "scenario": key,
                             "metrics": metrics, "checks": checks, "passed": passed})
                failed = [name for name, ok in checks.items() if not ok]
                print(f"{variant} seed={seed} {key}: {'PASS' if passed else 'FAIL'} {failed or ''}")
    passed = sum(run["passed"] for run in runs)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"settings": cfg.client, "shift_s": args.shift_s,
                               "passed": passed, "total": len(runs), "runs": runs}, indent=2), encoding="utf-8")
    print(f"{passed}/{len(runs)} passed -> {out}")
    if passed != len(runs):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
