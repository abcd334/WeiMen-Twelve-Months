"""Coverage audit, not a substitute for human literary/playtesting judgment."""
import argparse
from collections import Counter
import json
from pathlib import Path

from game_engine import current_thread, ending_view, mystery_complete
from simulate_balance import play_game
from models import GAME_VERSION
import case_engine

NIGHT_TYPES = {"personal_scene", "relationship_scene", "mainline_scene", "quiet_scene", "group_scene"}


def audit_game(state):
    scenes = state.scene_history
    nights = [s for s in scenes if s["type"] in NIGHT_TYPES]
    outcomes = [s["text"] for s in scenes if s["type"] == "outcome"]
    reactions = [s["text"] for s in scenes if s["type"] == "night_reaction"]
    month8 = next((s for s in scenes if s.get("scene_id") == "suspicion"), None)
    facts = {f["id"]: f for f in state.facts}
    grounded = bool(month8 and len(month8["evidence_ids"]) >= 2 and all(
        i in facts and facts[i]["month"] < 8 and facts[i]["text"] in month8["text"] for i in month8["evidence_ids"]))
    group = next((s for s in nights if s["type"] == "group_scene"), None)
    month9 = next((s for s in reversed(nights) if s["month"] <= 9), None)
    long_staying = [c for c in state.characters if c.status == "active" or not any(m["character_id"] == c.id and m["month"] <= 9 for m in state.major_outcomes)]
    distribution = {c.id: month9["spotlights"].get(c.id, 0) if month9 else 0 for c in long_staying}
    group_complete = bool(group and all(c.name in group["text"] for c in state.characters))
    end = ending_view(state)
    thread = current_thread(state)
    case_nights = []
    for night in nights:
        if not case_engine.is_case(state):
            continue
        day = next((d for d in state.case_history if d['phase'] == 'day' and d['month'] == night['month']), None)
        references = night.get('source_fact_ids', [])
        linked = bool(day and night.get('day_action_id') == day['action_id'] and references
                      and all(fid in day['fact_ids'] and fid in facts and facts[fid]['month'] == night['month'] for fid in references))
        reason = night.get('reason')
        if reason == 'evidence':
            content = bool(day and day['evidence_gained']) and all(state.evidence[cid]['text'] in night['text'] for cid in day['evidence_gained'])
        elif reason == 'source':
            ids = (day['claims_gained'] + day['lead_ids']) if day else []
            content = bool(ids) and any(n['text'] in night['text'] for n in state.claims + state.leads if n['id'] in ids)
        elif reason in ('deduction', 'final_council'):
            content = bool(day and day['deduction_result'] and day['deduction_result']['text'] in night['text'])
        else:
            content = reason in ('failure','injury','conflict','private') and bool(day) and bool(night.get('context'))
        case_nights.append(dict(month=night['month'], reason=reason, directly_linked=linked and content))
    return {"seed": state.seed, "thread": state.main_thread, "month_reached": state.month,
            "case_nights": case_nights,
            "case_night_link_percent": round(100 * sum(n['directly_linked'] for n in case_nights) / len(case_nights), 2) if case_nights else None,
            "mystery_axis": end['mystery_axis'], "sect_axis": end['sect_axis'],
            "callbacks_2_to_10": sum(2 <= c["month"] <= 10 for c in state.callback_history),
            "spotlights_before_10": distribution, "scene_counts": dict(Counter(s["type"] for s in nights)),
            "beats": sorted({b["beat"] for b in state.thread_beats}), "mystery_complete": mystery_complete(state),
            "repeated_outcomes": len(outcomes) - len(set(outcomes)), "outcome_count": len(outcomes),
            "repeated_reactions": len(reactions) - len(set(reactions)), "reaction_count": len(reactions),
            "unique_scene_texts": len({s["text"] for s in scenes}), "month8_grounded": grounded,
            "group_complete": group_complete, "ending_callback_count": len(end["callbacks"]),
            "final_scene_length": len(end["final_scene"]), "epilogue_lengths": [len(c["epilogue"]) for c in end["characters"]],
            "chain": [{"month": b["month"], "beat": b["beat"], "text": facts[b["fact_id"]]["text"]} for b in state.thread_beats],
            "callback_examples": state.callback_history[:4], "required_clues_found": [c for c in thread["required_clues"] if c in state.evidence],
            "investigation_count": len(state.investigation_history), "confirmed_count": len(state.evidence),
            "pending_count": len(state.leads), "claim_count": len(state.claims),
            "deduction_months": [d["month"] for d in state.deduction_history],
            "deductions_accepted": [d["month"] for d in state.deduction_history if d["accepted"]],
            "recovered_evidence": [e["id"] for e in state.evidence.values() if e.get('action_id', e['focus_id']).startswith("recover_")]}


def run_audit(count=200):
    rows = [audit_game(play_game(seed, "resource_guard_policy")) for seed in range(count)]
    complete = [r for r in rows if r["month_reached"] == 12]
    reached8 = [r for r in rows if r["month_reached"] >= 8]
    reached11 = [r for r in rows if r["month_reached"] >= 12]
    def rate(predicate, population):
        return round(100 * sum(predicate(r) for r in population) / len(population), 2) if population else None
    legacy_complete = [r for r in complete if r['thread'] != 'false_cards']
    legacy_reached8 = [r for r in reached8 if r['thread'] != 'false_cards']
    causal = [r for r in rows if r['thread'] == 'false_cards']
    report = {"version": GAME_VERSION, "seeds": count, "policy": "resource_guard_policy", "complete_games": len(complete),
              "case_games": len(causal),
              "case_night_link_percent": rate(lambda n: n['directly_linked'], [n for r in causal for n in r['case_nights']]),
              "case_games_meeting_80_percent": rate(lambda r: r['case_night_link_percent'] is not None and r['case_night_link_percent'] >= 80, causal),
              "deduction_checkpoint_percent": rate(lambda r: r["deduction_months"] == [4,8,11], complete),
              "complete_chain_percent": rate(lambda r: r["mystery_complete"], complete),
              "games_using_recovery": sum(bool(r["recovered_evidence"]) for r in rows),
              "thread_distribution": dict(Counter(r["thread"] for r in rows)),
              "average_callbacks": round(sum(r["callbacks_2_to_10"] for r in rows) / count, 2),
              "callback_coverage_percent": rate(lambda r: r["callbacks_2_to_10"] >= 3, complete),
              "spotlight_coverage_percent": rate(lambda r: all(v >= 2 for v in r["spotlights_before_10"].values()), complete),
              "relationship_coverage_percent": rate(lambda r: r["scene_counts"].get("relationship_scene", 0) >= 2, legacy_complete),
              "mainline_coverage_percent": rate(lambda r: r["scene_counts"].get("mainline_scene", 0) >= 2, complete),
              "month8_grounded_percent": rate(lambda r: r["month8_grounded"], legacy_reached8),
              "group_complete_percent": rate(lambda r: r["group_complete"], reached11),
              "ending_callbacks_percent": rate(lambda r: r["ending_callback_count"] >= 2, complete),
              "repeated_outcome_percent": round(100 * sum(r["repeated_outcomes"] for r in rows) / max(1, sum(r["outcome_count"] for r in rows)), 2),
              "repeated_night_reaction_percent": round(100 * sum(r["repeated_reactions"] for r in rows) / max(1, sum(r["reaction_count"] for r in rows)), 2),
              "average_unique_texts": round(sum(r["unique_scene_texts"] for r in rows) / count, 2),
              "thread_beat_coverage": {}, "examples": []}
    for thread_id in report["thread_distribution"]:
        cases = [r for r in rows if r["thread"] == thread_id]
        report["thread_beat_coverage"][thread_id] = {beat: rate(lambda r: beat in r["beats"], cases) for beat in ("setup", "escalation", "payoff")}
        example = next((r for r in cases if r["month_reached"] == 12), cases[0])
        report["examples"].append(example)
    return report, rows


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, default=200)
    parser.add_argument("--output", type=Path, default=Path("reports") / ("v" + GAME_VERSION))
    args = parser.parse_args()
    if args.seeds < 1:
        parser.error("seeds must be positive")
    report, rows = run_audit(args.seeds)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "narrative_coverage.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (args.output / "narrative_runs.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "examples"}, ensure_ascii=False, indent=2))
