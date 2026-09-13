"""Replayable v0.7 campaigns and a provenance audit; policies use public data."""
import argparse
from collections import Counter
import json
from pathlib import Path

import sect_engine as engine
from sect_models import date_label

OUT = Path(__file__).resolve().parent / "reports" / "v0.7"


def choose_plan(state, policy):
    view = engine.public_state(state)
    chars = {c["id"]: c for c in view["characters"]}
    active = [c for c in view["characters"] if c["active"]]
    able = [c for c in active if c["actionable"]]
    actions = [a for a in view["actions"] if a["cost"] <= view["resources"]["糧餉"]]
    by_id = {a["id"]: a for a in actions}
    personal = [a for a in actions if a["kind"] == "personal"]
    appointments = [a for a in actions if a["kind"] == "appoint"]
    chains = [a for a in actions if a["kind"] == "chain" and a["method"] == "ally"]
    choice = None
    if appointments:
        choice = appointments[0]
    elif state.tick % 4 == 0 and personal:
        choice = next((a for a in personal if a["event_id"] in ("suspicion", "memory_return", "goal")), personal[0])
    elif chains and state.tick % 2 == 0:
        choice = chains[0]
    elif state.tick in (7, 14, 21) and view["resources"]["糧餉"] >= 24:
        facility = "training" if policy == "mentor" else "lodge" if policy == "focus" else "herbs"
        choice = by_id.get("build/" + facility)
    if choice is None:
        if len(able) < 2:
            choice = by_id["rest"]
        elif view["resources"]["糧餉"] < 20:
            choice = by_id["work"]
        elif policy == "mentor" and state.tick % 3:
            choice = by_id["train"]
        else:
            missions = [a for a in actions if a["kind"] == "mission" and a["method"] == ("direct" if policy == "focus" else "supported")]
            skill_names = {"combat": "武力", "strategy": "智略", "medicine": "醫術", "diplomacy": "交涉"}
            choice = max(missions, key=lambda a: max(c["skills"][skill_names[a["skill"]]] for c in able)) if missions else by_id["work"]
    if choice.get("required"):
        ids = list(choice["required"])
    else:
        pool = active if choice.get("allow_injured") else able
        if choice["kind"] == "rest":
            pool = sorted(pool, key=lambda c: (-c["injury"], -c["fatigue"]))
        elif policy in ("focus", "mentor"):
            pool = sorted(pool, key=lambda c: (c["id"] != "c0" or c["fatigue"] >= 65, c["fatigue"]))
        else:
            pool = sorted(pool, key=lambda c: (len(c["experiences"]), c["fatigue"]))
        ids = [c["id"] for c in pool[:choice["maximum"]]]
        if len(ids) < choice["minimum"]:
            choice, ids = by_id["rest"], [c["id"] for c in active]
    jobs = {}
    others = [c for c in active if c["id"] not in ids]
    guard_assigned = False
    for char in others:
        if char["injury"] or char["fatigue"] >= 45 or not char["actionable"]:
            job = "rest"
        elif not guard_assigned:
            job = "guard"
            guard_assigned = True
        elif char["id"] == "c2":
            job = "herbs"
        else:
            job = "host"
        jobs[char["id"]] = job
    return choice["id"], ids, jobs


def run_campaign(seed, policy, turns=40, snapshots=None):
    state = engine.new_game(seed)
    for _ in range(turns):
        aid, team, jobs = choose_plan(state, policy)
        engine.resolve_turn(state, aid, team, jobs, f"{state.tick}:plan")
        if snapshots is not None and len(state.decisions) == 24:
            snapshots.append({"core_people": sum(c.stage >= 2 for c in state.characters),
                              "callbacks": len(state.callback_history)})
        if state.phase == "ended":
            break
        engine.next_tick(state, f"{state.tick}:next")
    return state


def audit(state):
    memories = {m.id: m for m in state.shared_memories}
    experiences = {e.id: (c.id, e) for c in state.characters for e in c.experiences}
    for memory in memories.values():
        assert len(memory.participants) == len(set(memory.participants)) >= 2
        assert memory.source_ids and all(source in experiences for source in memory.source_ids)
        assert all(experiences[source][0] in memory.participants for source in memory.source_ids)
        assert all(experiences[source][1].tick == memory.tick for source in memory.source_ids)
    for callback in state.callback_history:
        memory = memories[callback["source_id"]]
        assert callback["tick"] - memory.tick >= 3
        assert callback["source_tick"] == memory.tick
        assert set(callback["participants"]) == set(memory.participants)
        if callback["event_id"] == "suspicion":
            assert "rescue" in memory.tags and memory.actor_id and memory.target_id
    for outcome in state.major_outcomes:
        assert len(outcome["warnings"]) >= 2 and max(outcome["warnings"]) < outcome["tick"]
    for char in state.characters:
        assert char.narrative_weight == sum(char.weight_sources.values())
        assert 0 <= char.injury <= 2 and 0 <= char.fatigue <= 100
    assert len(state.resolved) == len(state.decisions)


def reading(state, policy):
    lines = [f"# v0.7 閱讀稿 · 種子 {state.seed} · {policy}", "",
             "此稿由實際引擎決策產生。先閱讀經歷，再回答：這局你最記得誰？為什麼？", ""]
    for scene, decision in zip(state.scene_history, state.decisions):
        lines.extend([f"## {date_label(scene['tick'])} · {decision['label']}", "",
                      "參與：" + "、".join(state.character(cid).name for cid in decision["participants"]), ""])
        lines.extend(scene["text"])
        lines.append("")
    lines.extend(["## 門人的經歷", ""])
    for char in engine.history_review(state):
        lines.extend([f"### {char['name']} · {char['stage']}", "", *char["story"], ""])
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, default=30)
    parser.add_argument("--turns", type=int, default=40)
    args = parser.parse_args()
    if args.seeds < 1 or args.turns < 1:
        parser.error("seeds and turns must be positive")
    OUT.mkdir(parents=True, exist_ok=True)
    rows, coverage, counts = [], Counter(), Counter()
    samples = {}
    for policy in ("focus", "rotation", "mentor"):
        for seed in range(args.seeds):
            snapshots = []
            state = run_campaign(seed, policy, args.turns, snapshots)
            audit(state)
            row = dict(seed=seed, policy=policy, decisions=len(state.decisions), ending=state.ending,
                       callbacks=len(state.callback_history), memories=len(state.shared_memories),
                       core_people=sum(c.stage >= 2 for c in state.characters),
                       offices=[c.name + "：" + c.office for c in state.characters if c.office],
                       entered_year_two=state.tick > 36, resources=state.resources)
            row["at_24_decisions"] = snapshots[0] if snapshots else None
            rows.append(row)
            for scene in state.scene_history:
                coverage[scene["event_id"]] += 1
            counts["callback_runs"] += bool(state.callback_history)
            counts["core_runs"] += row["core_people"] > 0
            counts["year_two_runs"] += row["entered_year_two"]
            if seed == 4 or (seed == 0 and args.seeds <= 4):
                samples[policy] = state
                (OUT / f"reading_{policy}.md").write_text(reading(state, policy), encoding="utf-8")
    summary = dict(campaigns=len(rows), turns=args.turns, counts=dict(counts), coverage=dict(coverage), runs=rows)
    (OUT / "simulation.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    replays = {policy: {"seed": s.seed, "version": s.version, "decisions": s.decisions} for policy, s in samples.items()}
    (OUT / "replays.json").write_text(json.dumps(replays, ensure_ascii=False, indent=2), encoding="utf-8")
    # Replay the recorded actions independently instead of re-running the policy.
    for policy, original in samples.items():
        replay = engine.new_game(original.seed)
        for decision in original.decisions:
            engine.resolve_turn(replay, decision["action_id"], decision["participants"], decision["assignments"])
            if replay.phase == "result":
                engine.next_tick(replay)
        assert engine.public_state(replay) == engine.public_state(original)
        assert replay.rng.getstate() == original.rng.getstate()
    print(json.dumps({"campaigns": len(rows), **counts, "replays_verified": len(samples), "event_kinds": len(coverage)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
