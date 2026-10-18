"""Run one complete evaluation on the bundled sample PDFs from the command line.

Usage:
    python scripts/run_sample.py                       # offline demo evaluator
    python scripts/run_sample.py --provider anthropic  # needs ANTHROPIC_API_KEY
    python scripts/run_sample.py --provider openai     # needs OPENAI_API_KEY (+ OPENAI_BASE_URL optional)
    python scripts/run_sample.py --inject-fault "Zenith CloudWorks"

Writes the exported JSON to sample_output/ and prints the leaderboard.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from rfp_agent import database as db  # noqa: E402
from rfp_agent.evaluation_agent import (AnthropicProvider, EvaluationAgent, FaultInjectingProvider,  # noqa: E402
                                        OfflineDemoProvider, OpenAICompatProvider)
from rfp_agent.orchestrator import Orchestrator, SupplierSubmission  # noqa: E402
from rfp_agent.samples import SAMPLE_SUPPLIERS  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", choices=["offline", "anthropic", "openai"], default="offline")
    ap.add_argument("--model", default=None)
    ap.add_argument("--db", default=str(ROOT / "db" / "rfp_evaluation.db"))
    ap.add_argument("--inject-fault", action="append", default=[], metavar="SUPPLIER")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    if args.provider == "anthropic":
        provider = AnthropicProvider(api_key=os.environ["ANTHROPIC_API_KEY"],
                                     **({"model": args.model} if args.model else {}))
    elif args.provider == "openai":
        provider = OpenAICompatProvider(api_key=os.environ["OPENAI_API_KEY"],
                                        base_url=os.environ.get("OPENAI_BASE_URL"),
                                        **({"model": args.model} if args.model else {}))
    else:
        provider = OfflineDemoProvider()
    if args.inject_fault:
        provider = FaultInjectingProvider(provider, set(args.inject_fault))

    conn = db.connect(args.db)
    db.init_db(conn)
    subs = [SupplierSubmission(s["supplier_name"], s["submission_date"], s["experience_rating"], s["file"],
                               (ROOT / "sample_rfps" / s["file"]).read_bytes()) for s in SAMPLE_SUPPLIERS]
    result = Orchestrator(conn, EvaluationAgent(provider),
                          progress=lambda m, f: print(f"[{f:4.0%}] {m}")).run(subs)

    out = Path(args.out) if args.out else ROOT / "sample_output" / f"{result['rfp_run_id']}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\nRFP_RUN_ID: {result['rfp_run_id']}  ({result['llm']['provider']} / {result['llm']['model']})")
    print(f"{'Rank':<6}{'Supplier':<22}{'Absolute':>9}{'PPI':>8}  {'Submitted':<12}{'Exp':>4}")
    for s in result["suppliers"]:
        print(f"{s['final_rank']:<6}{s['supplier_name']:<22}{s['absolute_score']:>9.2f}{s['ppi']:>8.2f}  "
              f"{s['submission_date']:<12}{s['experience_rating']:>4g}")
    print(f"\nWarnings: {len(result['warnings'])}")
    for w in result["warnings"]:
        print(f"  - {w}")
    print(f"\nJSON written to {out}")


if __name__ == "__main__":
    main()
