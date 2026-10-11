"""Stage 6 eval harness.

    python evals/run_evals.py --offline            # free: labels vs rubric on the fact key
    python evals/run_evals.py --runs 3             # live: adds Claude extraction and vendor review
    python evals/run_evals.py --rescore 20261010-210739   # free: re-score saved live outputs

Writes evals/RESULTS.md (summary, committed) and evals/DISAGREEMENTS.md (the
log for refining the rubric). Raw per-run outputs go to evals/results/
(git-ignored). Every use case is assessed as if it runs in an approved
zero-retention tool, matching how the cases were labeled.
"""

import argparse
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ai_governance import llm  # noqa: E402
from ai_governance.clauses import parse_documents  # noqa: E402
from ai_governance.eval_metrics import compare, dimension_agreement, score_gaps, score_tiers  # noqa: E402
from ai_governance.intake import Finding, IntakeResult, Profile, ProfileField, answer_follow_ups, run_intake  # noqa: E402
from ai_governance.rubric import Rubric, Tier, load_rubric  # noqa: E402
from ai_governance.tiering import TierResult, ToolRecord, assess  # noqa: E402
from ai_governance.vendor import VendorReviewResult, review  # noqa: E402

EVALS = ROOT / "evals"
EVAL_TOOL = ToolRecord(name="eval tool", vendor_handling_level="enterprise_zdr", listed_as_approved=True)


def key_intake(case: dict, rubric: Rubric) -> IntakeResult:
    """The fact key as if extraction were perfect."""
    answers = {d: [Finding(level_id=lv, quote="(fact key)", basis="stated") for lv in levels]
               for d, levels in case["facts"].items()}
    intake_dims = [d.id for d in rubric.dimensions if d.source == "intake"]
    return IntakeResult(description=case["text"],
                        profile=Profile(**{f: ProfileField(value=None, quote=None) for f in Profile.model_fields}),
                        answers=answers, unknown_dimensions=[d for d in intake_dims if d not in answers],
                        needs_review=[], rejected=[], follow_ups=[])


def describe_ratings(result: TierResult) -> str:
    return ", ".join(f"{r.dimension_id}={r.tier.value}" + (f" ({r.driver_level})" if r.driver_level else " (unknown)")
                     for r in result.ratings if r.source != "register")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline", action="store_true", help="no API calls: labels vs rubric on the fact key only")
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--part", choices=["all", "use_cases", "vendors"], default="all")
    parser.add_argument("--rescore", metavar="RUN_DIR", help="re-score saved outputs in evals/results/RUN_DIR (no API calls)")
    args = parser.parse_args()

    rubric = load_rubric()
    cases = yaml.safe_load((EVALS / "use_cases.yaml").read_text(encoding="utf-8"))["cases"]
    labels = json.loads((EVALS / "labels.json").read_text(encoding="utf-8"))
    stamp = args.rescore or datetime.now().strftime("%Y%m%d-%H%M%S")
    raw_dir = EVALS / "results" / stamp
    live = not args.offline
    recorder = llm.CostRecorder()
    report, log = [], []

    report += ["# Eval results", "",
               f"Run {stamp}. Model `{llm.MODEL}`. "
               + ("Offline: no API calls." if args.offline else
                  "Re-scored from saved outputs of that run (no new API calls)." if args.rescore else
                  f"{args.runs} run(s) per case."),
               "", "Synthetic data only. Labels set by the rubric owner, blind to the rubric's computed tiers. "
               "Every use case is assessed as if run in an approved zero-retention tool.", ""]

    # ----- use cases -----------------------------------------------------------
    if args.part in ("all", "use_cases"):
        key_results = {c["id"]: assess(key_intake(c, rubric), EVAL_TOOL, rubric) for c in cases}
        label = {c["id"]: Tier(labels["use_cases"][c["id"]]) for c in cases}
        intakes: dict[str, list[IntakeResult]] = {c["id"]: [] for c in cases}

        if args.rescore:
            for c in cases:
                for path in sorted(raw_dir.glob(f"{c['id']}-run*.json")):
                    intakes[c["id"]].append(IntakeResult.model_validate_json(path.read_text(encoding="utf-8")))
        elif live:
            raw_dir.mkdir(parents=True, exist_ok=True)
            for run in range(args.runs):
                for c in cases:
                    intake = run_intake(c["text"], rubric, call=recorder)
                    (raw_dir / f"{c['id']}-run{run + 1}.json").write_text(intake.model_dump_json(indent=2), encoding="utf-8")
                    intakes[c["id"]].append(intake)
                print(f"use cases run {run + 1}/{args.runs} done, cost so far ${recorder.cost:.3f}", file=sys.stderr)

        # Scored twice: as extracted (provisional where facts are unknown), and after the
        # follow-up questions are answered from the fact key, as an honest requester would.
        # Answers only add facts, so wrong findings the model asserted still count.
        case_by_id = {c["id"]: c for c in cases}

        def answered(i: str, intake: IntakeResult) -> IntakeResult:
            facts = case_by_id[i]["facts"]
            return answer_follow_ups(intake, {d: facts[d] for d in intake.unknown_dimensions if d in facts}, rubric)

        pipeline = {i: [assess(x, EVAL_TOOL, rubric) for x in xs] for i, xs in intakes.items()}
        settled = {i: [assess(answered(i, x), EVAL_TOOL, rubric) for x in xs] for i, xs in intakes.items()}

        rubric_score = score_tiers([(label[i], key_results[i].tier) for i in label])
        rows = [("Rubric on fact key vs your labels", rubric_score)]
        if live:
            for name, results in [("as extracted (provisional tiers)", pipeline),
                                  ("after follow-ups answered", settled)]:
                rows.append((f"Pipeline {name} vs your labels",
                             score_tiers([(label[i], p.tier) for i in label for p in results[i]])))
                rows.append((f"Pipeline {name} vs rubric on fact key (extraction only)",
                             score_tiers([(key_results[i].tier, p.tier) for i in label for p in results[i]])))

        report += ["## Use cases: tiers", "",
                   "| Comparison | n | Match | False Low (dangerous) | Over-escalation (friction) |",
                   "|---|---|---|---|---|"]
        report += [f"| {name} | {s.n} | {s.match} ({s.match_rate:.0%}) | {s.false_low} ({s.false_low_rate:.0%}) | "
                   f"{s.over_escalation} ({s.over_escalation_rate:.0%}) |" for name, s in rows]

        if live:
            agree = Counter()
            total = Counter()
            for i in label:
                for p in settled[i]:
                    for dim, ok in dimension_agreement(key_results[i], p).items():
                        total[dim] += 1
                        agree[dim] += ok
            report += ["", "## Use cases: extraction accuracy per dimension", "",
                       "Share of case-runs where the extracted facts, after follow-ups were answered from the fact key, "
                       "gave the same dimension rating as the fact key. Remaining differences are findings the model "
                       "asserted that the key does not support (answers can only add facts, never remove them).", "",
                       "| Dimension | Agreement |", "|---|---|"]
            report += [f"| {d} | {agree[d]}/{total[d]} ({agree[d] / total[d]:.0%}) |" for d in total]

        report += ["", "## Use cases: per case", "",
                   "| Case | Your label | Rubric on key | Pipeline as extracted | Pipeline after follow-ups |",
                   "|---|---|---|---|---|"]
        for c in cases:
            i = c["id"]
            runs = ", ".join(p.tier.value + (" (prov.)" if p.provisional else "") for p in pipeline[i]) or "n/a"
            done = ", ".join(p.tier.value for p in settled[i]) or "n/a"
            report.append(f"| {i} {c['title']} | {label[i].value} | {key_results[i].tier.value} | {runs} | {done} |")

        log += ["# Disagreement log", "", "Generated by `evals/run_evals.py`. Use it to refine `governance/rubric.yaml`.", "",
                "## Rubric vs your labels (the rubric, applied to the correct facts, disagrees with you)", ""]
        for c in cases:
            i = c["id"]
            outcome = compare(label[i], key_results[i].tier)
            if outcome != "match":
                log += [f"### {i} {c['title']}: you {label[i].value}, rubric {key_results[i].tier.value} "
                        f"({outcome.replace('_', ' ')})", "",
                        *[f"- {r}" for r in key_results[i].reasons],
                        f"- Dimension ratings: {describe_ratings(key_results[i])}", ""]
        if live:
            log += ["## Extraction errors (after follow-ups answered, pipeline facts still differ from the fact key)", ""]
            for c in cases:
                i = c["id"]
                for n, p in enumerate(settled[i], 1):
                    wrong = [d for d, ok in dimension_agreement(key_results[i], p).items() if not ok]
                    if wrong:
                        key_by = {r.dimension_id: r for r in key_results[i].ratings}
                        pipe_by = {r.dimension_id: r for r in p.ratings}
                        log += [f"### {i} run {n}: tier {p.tier.value} (key {key_results[i].tier.value})", ""]
                        log += [f"- {d}: extracted {pipe_by[d].tier.value} ({pipe_by[d].driver_level or 'unknown'}), "
                                f"key {key_by[d].tier.value} ({key_by[d].driver_level})" for d in wrong]
                        log.append("")

    # ----- vendors ---------------------------------------------------------------
    if args.part in ("all", "vendors") and live:
        requirement_ids = [r.id for r in rubric.vendor_requirements]
        rows_all, per_vendor = [], []
        for name, gaps in labels["vendors"].items():
            files = sorted((EVALS / "vendors" / name).iterdir())
            if args.rescore:
                saved = [VendorReviewResult.model_validate_json(p.read_text(encoding="utf-8"))
                         for p in sorted(raw_dir.glob(f"vendor-{name}-run*.json"))]
            else:
                saved = []
                for run in range(args.runs):
                    result = review(parse_documents(files), rubric, call=recorder)
                    (raw_dir / f"vendor-{name}-run{run + 1}.json").write_text(result.model_dump_json(indent=2), encoding="utf-8")
                    saved.append(result)
            for run, result in enumerate(saved):
                predicted = {r.id for r in result.requirements if r.outcome == "gap"}
                rows = [(rid in gaps, rid in predicted) for rid in requirement_ids]
                rows_all += rows
                missed = [rid for rid in requirement_ids if rid in gaps and rid not in predicted]
                false = [rid for rid in requirement_ids if rid in predicted and rid not in gaps]
                per_vendor.append((name, run + 1, result.proposed_vendor_level, result.approvable, missed, false))
            print(f"vendor {name} done, cost so far ${recorder.cost:.3f}", file=sys.stderr)
        s = score_gaps(rows_all)
        report += ["", "## Vendor terms review", "",
                   f"Requirement-level accuracy: {s.correct}/{s.n} ({s.accuracy:.0%}). "
                   f"**Missed gaps (dangerous): {s.missed_gaps}.** False gaps (friction): {s.false_gaps}.", "",
                   "| Vendor | Run | Proposed level | Approvable | Missed gaps | False gaps |", "|---|---|---|---|---|---|"]
        report += [f"| {n} | {r} | {lvl} | {'yes' if ok else 'no'} | {', '.join(m) or 'none'} | {', '.join(f) or 'none'} |"
                   for n, r, lvl, ok, m, f in per_vendor]

    if live and not args.rescore:
        report += ["", f"Total API cost for this run: about ${recorder.cost:.2f}."]
    elif args.rescore:
        report += ["", "Live run cost (from its log): about $0.85 for 3 runs of 20 use cases and 5 vendors."]
    (EVALS / "RESULTS.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    (EVALS / "DISAGREEMENTS.md").write_text("\n".join(log) + "\n", encoding="utf-8")
    print("\n".join(report))


if __name__ == "__main__":
    main()
