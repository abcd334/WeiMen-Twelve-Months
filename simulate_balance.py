"""Headless public-information policies and reproducible balance/audit reports."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
from random import Random
from investigation import public_investigations, checkpoint_view, resolve_deduction

from game_engine import (ENDINGS, begin_month, emergency_rest, legal_actions, new_game,
                         night_view, resolve_day, resolve_night, start_night)

POLICIES = ("random_policy", "highest_skill_policy", "conservative_policy", "resource_guard_policy")
RISK_ORDER = {"low": 0, "medium": 1, "high": 2, "lethal": 3}


def visible_fatigue(state, char):
    text = char.physical(state.month)
    return 2 if "十分疲憊" in text else 1 if "疲勞" in text or "輕傷" in text else 0


def choose_day(state, policy, policy_rng):
    actions = legal_actions(state)
    if not actions:
        return None
    if policy == "random_policy":
        # Uniform options first, then uniform teams: two-person options have more combinations.
        ids = list(dict.fromkeys(o["id"] for o, _ in actions))
        option_id = policy_rng.choice(ids)
        return policy_rng.choice([a for a in actions if a[0]["id"] == option_id])
    lowest = min(state.resources, key=state.resources.get)

    def rank(action):
        option, ids = action
        team = [state.character(cid) for cid in ids]
        skill = sum(c.skills[option["skill"]] for c in team) / len(team)
        fatigue = sum(visible_fatigue(state, c) for c in team)
        if policy == "highest_skill_policy":
            return (skill, -fatigue, -option["cost"])
        if policy == "conservative_policy":
            critical = sum(c.role in ("combat", "strategy") for c in team)
            return (-RISK_ORDER[option["risk"]], -fatigue, -critical, skill, -option["cost"])
        return (option["focus"] == lowest, -option["cost"] if lowest == "treasury" else 0,
                skill - fatigue * 0.5, -RISK_ORDER[option["risk"]])
    best = max(rank(a) for a in actions)
    return policy_rng.choice([a for a in actions if rank(a) == best])


def choose_night(state, policy, policy_rng):
    scene = night_view(state)
    available = [c for c in scene["choices"] if c["cost"] <= state.resources["treasury"]]
    choices = [c["id"] for c in available]
    def select(approach):
        return next((c["id"] for c in available if c["approach"] == approach), choices[0])
    char = state.character(scene["character_id"])
    if policy == "random_policy":
        return policy_rng.choice(choices)
    if policy == "resource_guard_policy":
        return select("discipline" if state.resources["treasury"] < 38 or state.resources["defense"] < 45 else "support")
    if policy == "conservative_policy":
        return select("support" if visible_fatigue(state, char) and state.resources["treasury"] > 18 else "discipline")
    if char.personality in ("剛直", "謹慎") or state.resources["treasury"] < 25:
        return select("discipline")
    return select("support")


def choose_focus(state, policy, policy_rng, action):
    budget = state.resources["treasury"] - action[0]["cost"]
    options = [o for o in public_investigations(state) if o["cost"] < budget]
    if policy == "random_policy":
        return policy_rng.choice(options)["id"] if options else "none"
    if policy == "resource_guard_policy" and budget < 20:
        return "none"
    fresh = [o for o in options if not o["already_known"] and o["id"] != "none"]
    if policy == "conservative_policy":
        return next((o["id"] for o in fresh if o["cost"] <= 1), "none")
    return next((o["id"] for o in fresh if o["label"].startswith("逐項補查")), next((o["id"] for o in fresh if o["cost"] == 2), fresh[0]["id"] if fresh else "none"))


def choose_deduction(state, policy, policy_rng):
    # Read only the checkpoint projection, never the answer graph or hidden truth.
    view = checkpoint_view(state)
    known = view["evidence"]
    if state.month == 4:
        hypothesis = "uncertain"
        if policy == "random_policy":
            hypothesis = policy_rng.choice(view["hypotheses"])["id"]
        elif known and policy != "conservative_policy":
            texts = "".join(e["text"] for e in known)
            label = "名帖遭人偽造" if "印" in texts and "不符" in texts else "通信可能延續前掌門的聯絡" if "通信" in texts or "收件" in texts else "有人利用封路掩護運貨" if "換防圖" in texts or "測量" in texts else "目前證據不足"
            hypothesis = next((h["id"] for h in view["hypotheses"] if h["label"] == label), "uncertain")
        return {"hypothesis":hypothesis}
    count = 2 if state.month == 8 else 3
    if policy == "random_policy":
        return {"evidence_ids":[e["id"] for e in policy_rng.sample(known,count)] if len(known) >= count else []}
    selected=[]
    for slot in ("document","physical","witness")[:count]:
        choices=[e for e in known if e["type"]==slot]
        choices.sort(key=lambda e:not any(word in e["title"] for word in ("用印", "墨樣", "核對證詞", "換防", "測量", "通行", "收件", "原始留底", "回信")))
        if choices:
            selected.append(choices[0]["id"])
    return {"evidence_ids":selected if len(selected)==count else []}


def audit_outcomes(state):
    cues = {c.id: c for c in state.observations}
    rows = []
    for outcome in state.major_outcomes:
        char = state.character(outcome["character_id"])
        row = {"seed": state.seed, "month": outcome["month"], "name": char.name, "kind": outcome["kind"]}
        if outcome["kind"] == "dead":
            assert "致命風險" in outcome["risk_notice"]
            row["risk_notice"] = outcome["risk_notice"]
        else:
            warnings = [cues[i] for i in outcome["warnings"]]
            assert len({c.month for c in warnings}) >= 2
            assert any(c.strength == "strong" for c in warnings)
            assert all(c.month < outcome["month"] and c.evidence["supported"] for c in warnings)
            assert all(c.strength != "noise" for c in warnings)
            row["warnings"] = [{"month": c.month, "strength": c.strength, "text": c.text} for c in warnings]
        rows.append(row)
    return rows


def play_game(seed, policy):
    state = new_game(seed)
    # Policy randomness never advances the game's Random object. Replaying the
    # same seed and recorded actions in the UI therefore gives identical results.
    policy_rng = Random(seed ^ 0x574549)
    while not state.ending:
        if state.phase == "day":
            action = choose_day(state, policy, policy_rng)
            if action:
                resolve_day(state, action[0]["id"], action[1], focus_id=choose_focus(state,policy,policy_rng,action))
            else:
                emergency_rest(state)
        elif state.phase == "day_result":
            start_night(state)
        elif state.phase == "night":
            resolve_night(state, choose_night(state, policy, policy_rng))
        elif state.phase == "deduction":
            resolve_deduction(state, **choose_deduction(state,policy,policy_rng))
        elif state.phase in ("night_result", "deduction_result"):
            begin_month(state)
    audit_outcomes(state)
    return state


def simulate(games_per_policy=250, seed_start=0):
    report = {"version": "0.5", "games_per_policy": games_per_policy, "seed_start": seed_start,
              "total_games": games_per_policy * len(POLICIES), "policies": {}, "fairness_examples": []}
    for policy in POLICIES:
        counts, totals, outcomes = Counter(), Counter(), Counter()
        options = defaultdict(lambda: {"selected": 0, "success": 0})
        examples = []
        for seed in range(seed_start, seed_start + games_per_policy):
            state = play_game(seed, policy)
            counts[state.ending] += 1
            totals.update(state.resources)
            totals["remaining"] += len(state.active())
            outcomes.update(state.counters)
            for row in state.option_stats:
                key = row["event"] + "/" + row["option"]
                options[key]["selected"] += 1
                options[key]["success"] += int(row["success"])
            for row in audit_outcomes(state):
                if len(examples) < 6 and not any(e["seed"] == seed for e in examples):
                    row["policy"] = policy
                    examples.append(row)
        report["policies"][policy] = {
            "endings": {e: {"count": counts[e], "percent": round(100 * counts[e] / games_per_policy, 2)} for e in ENDINGS},
            "averages": {k: round(totals[k] / games_per_policy, 2) for k in ("remaining", "treasury", "defense", "reputation")},
            "outcomes": dict(outcomes), "options": dict(sorted(options.items()))}
        report["fairness_examples"].extend(examples)
    report["ending_leaders"] = {e: sorted(POLICIES, key=lambda p: report["policies"][p]["endings"][e]["count"], reverse=True) for e in ENDINGS}
    return report


def summary_markdown(report):
    lines = ["# 平衡模擬結果", "", f"每策略 {report['games_per_policy']} 局；共 {report['total_games']} 局。種子從 {report['seed_start']} 起連續取樣。", "",
             "| 策略 | 揭破陰謀 | 聯盟退敵 | 正面取勝 | 慘勝守山 | 門派覆滅 | 平均留門人數 | 糧餉 | 防備 | 聲望 |",
             "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for name, result in report["policies"].items():
        values = [f"{result['endings'][e]['percent']}%" for e in ENDINGS]
        values += [str(result["averages"][k]) for k in ("remaining", "treasury", "defense", "reputation")]
        lines.append("| " + name + " | " + " | ".join(values) + " |")
    lines += ["", "| 策略 | 永久離開 | 倒戈／背叛 | 重傷次數 | 死亡 |", "|---|---:|---:|---:|---:|"]
    for name, result in report["policies"].items():
        lines.append("| " + name + " | " + " | ".join(str(result["outcomes"].get(k, 0)) for k in ("left", "defected", "severe_injury", "dead")) + " |")
    lines += ["", "各事件選項的選取／成功次數與跨種子公平性案例，完整保存於 balance_report.json。", "",
              "所有重大人物後果皆經自動稽核：離開與倒戈有不同月份的前置警示且至少一條強線索；死亡有派遣前致命風險提示。", "",
              "## 結局較常由哪些策略達成", ""]
    for ending, leaders in report["ending_leaders"].items():
        lines.append(f"- {ending}：" + "、".join(f"{p}（{report['policies'][p]['endings'][ending]['percent']}%）" for p in leaders))
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--games-per-policy", type=int, default=250)
    parser.add_argument("--seed-start", type=int, default=0)
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parent / "reports")
    args = parser.parse_args()
    if args.games_per_policy < 1:
        parser.error("games-per-policy must be positive")
    result = simulate(args.games_per_policy, args.seed_start)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "balance_report.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    (args.output / "balance_summary.md").write_text(summary_markdown(result), encoding="utf-8")
    print(summary_markdown(result))
