#!/usr/bin/env python3
# evals/harness.py
"""
Evaluation harness: computes precision, recall, and FP rate against labeled ground truth.

Usage:
    python evals/harness.py --scan-id <uuid>
    python evals/harness.py --findings-file <path-to-findings.json>
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
from dataclasses import dataclass


@dataclass
class EvalResult:
    true_positives: int
    false_positives: int
    false_negatives: int

    @property
    def precision(self) -> float:
        total = self.true_positives + self.false_positives
        return self.true_positives / total if total > 0 else 0.0

    @property
    def recall(self) -> float:
        total = self.true_positives + self.false_negatives
        return self.true_positives / total if total > 0 else 0.0

    @property
    def fp_rate(self) -> float:
        total = self.true_positives + self.false_positives
        return self.false_positives / total if total > 0 else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) > 0 else 0.0


def _finding_matches_ground_truth(finding: dict, gt: dict) -> bool:
    rule_id = (finding.get("rule_id") or "").lower()
    file_path = (finding.get("location") or {}).get("file", "")
    line = (finding.get("location") or {}).get("line_start", 0)
    cwe = finding.get("cwe") or ""

    rule_match = gt["rule_pattern"].lower() in rule_id
    file_match = gt["file"] in file_path
    line_match = abs(line - gt["line_start"]) <= 3  # ±3 line tolerance
    # cwe_match used only when cwe is present in finding
    cwe_match = gt["cwe"] == cwe if cwe else True  # noqa: F841 (kept for future use)

    return rule_match and file_match and line_match


def evaluate(findings: list[dict], ground_truth_path: str) -> EvalResult:
    gt_data = json.loads(Path(ground_truth_path).read_text())
    known = gt_data["known_findings"]

    open_findings = [f for f in findings if f.get("status") != "dismissed"]

    matched_gt: set[int] = set()
    matched_findings: set[int] = set()

    for i, gt in enumerate(known):
        for j, finding in enumerate(open_findings):
            if _finding_matches_ground_truth(finding, gt):
                matched_gt.add(i)
                matched_findings.add(j)
                break

    tp = len(matched_gt)
    fn = len(known) - tp
    fp = len(open_findings) - len(matched_findings)

    return EvalResult(true_positives=tp, false_positives=fp, false_negatives=fn)


def main() -> None:
    parser = argparse.ArgumentParser(description="Argus evaluation harness")
    parser.add_argument("--findings-file", help="Path to JSON file with findings array")
    parser.add_argument("--scan-id", help="Scan ID to fetch from running API")
    parser.add_argument(
        "--ground-truth",
        default="evals/fixtures/ground_truth.json",
        help="Path to ground truth JSON",
    )
    args = parser.parse_args()

    if args.findings_file:
        findings = json.loads(Path(args.findings_file).read_text())
    elif args.scan_id:
        import httpx

        api_base = "http://localhost:8000"
        resp = httpx.get(f"{api_base}/api/v1/scans/{args.scan_id}/findings")
        resp.raise_for_status()
        findings = resp.json()
    else:
        print("Error: --findings-file or --scan-id required", file=sys.stderr)
        sys.exit(1)

    result = evaluate(findings, args.ground_truth)

    print(f"\n{'='*50}")
    print(f"  Argus Evaluation Report")
    print(f"{'='*50}")
    print(f"  True Positives:  {result.true_positives}")
    print(f"  False Positives: {result.false_positives}")
    print(f"  False Negatives: {result.false_negatives}")
    print(f"{'─'*50}")
    print(f"  Precision:  {result.precision:.1%}")
    print(f"  Recall:     {result.recall:.1%}")
    print(f"  FP Rate:    {result.fp_rate:.1%}")
    print(f"  F1 Score:   {result.f1:.1%}")
    print(f"{'='*50}\n")

    # Fail if FP rate is too high (build-breaking threshold)
    if result.fp_rate > 0.40:
        print(
            f"FAIL: FP rate {result.fp_rate:.1%} exceeds 40% threshold",
            file=sys.stderr,
        )
        sys.exit(1)

    print("PASS")


if __name__ == "__main__":
    main()
