"""Coverage audit, not a substitute for human literary/playtesting judgment."""
import argparse
from collections import Counter
import json
from pathlib import Path

from game_engine import current_thread, ending_view, mystery_complete
from simulate_balance import play_game

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
    return {"seed": state.seed, "thread": state.main_thread, "month_reached": state.month,
            "callbacks_2_to_10": sum(2 <= c["month"] <= 10 for c in state.callback_history),
            "spotlights_before_10": distribution, "scene_counts": dict(Counter(s["type"] for s in nights)),
            "beats": sorted({b["beat"] for b in state.thread_beats}), "mystery_complete": mystery_complete(state),
            "repeated_outcomes": len(outcomes) - len(set(outcomes)), "outcome_count": len(outcomes),
            "repeated_reactions": len(reactions) - len(set(reactions)), "reaction_count": len(reactions),
            "unique_scene_texts": len({s["text"] for s in scenes}), "month8_grounded": grounded,
            "group_complete": group_complete, "ending_callback_count": len(end["callbacks"]),
            "final_scene_length": len(end["final_scene"]), "epilogue_lengths": [len(c["epilogue"]) for c in end["characters"]],
            "chain": [{"month": b["month"], "beat": b["beat"], "text": facts[b["fact_id"]]["text"]} for b in state.thread_beats],
            "callback_examples": state.callback_history[:4], "required_clues_found": [c for c in thread["required_clues"] if c in state.intel]}


def run_audit(count=200):
    rows = [audit_game(play_game(seed, "resource_guard_policy")) for seed in range(count)]
    complete = [r for r in rows if r["month_reached"] == 12]
    reached8 = [r for r in rows if r["month_reached"] >= 8]
    reached11 = [r for r in rows if r["month_reached"] >= 12]
    def rate(predicate, population):
        return round(100 * sum(predicate(r) for r in population) / len(population), 2) if population else None
    report = {"seeds": count, "policy": "resource_guard_policy", "complete_games": len(complete),
              "thread_distribution": dict(Counter(r["thread"] for r in rows)),
              "average_callbacks": round(sum(r["callbacks_2_to_10"] for r in rows) / count, 2),
              "callback_coverage_percent": rate(lambda r: r["callbacks_2_to_10"] >= 3, complete),
              "spotlight_coverage_percent": rate(lambda r: all(v >= 2 for v in r["spotlights_before_10"].values()), complete),
              "relationship_coverage_percent": rate(lambda r: r["scene_counts"].get("relationship_scene", 0) >= 2, complete),
              "mainline_coverage_percent": rate(lambda r: r["scene_counts"].get("mainline_scene", 0) >= 2, complete),
              "month8_grounded_percent": rate(lambda r: r["month8_grounded"], reached8),
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
    parser.add_argument("--output", type=Path, default=Path("reports"))
    args = parser.parse_args()
    if args.seeds < 1:
        parser.error("seeds must be positive")
    report, rows = run_audit(args.seeds)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "narrative_coverage.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (args.output / "narrative_runs.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "examples"}, ensure_ascii=False, indent=2))
