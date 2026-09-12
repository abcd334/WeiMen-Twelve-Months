"""Reproducible, agent-directed reading transcripts; not human playtest evidence."""
import json
from pathlib import Path
from random import Random

from game_engine import (begin_month, current_event, emergency_rest, ending_view,
                         legal_actions, new_game, night_view, public_state,
                         resolve_day, resolve_night, start_night)
from simulate_balance import audit_outcomes, choose_day, choose_night, choose_focus, choose_deduction, play_game
from investigation import checkpoint_view, resolve_deduction

PLANS = {
    0: {1: "ledger", 4: "investigate", 8: "watch"},
    4: {1: "ledger", 4: "appeal", 8: "open"},
    6: {1: "repair", 4: "investigate", 8: "watch"},
}


def run_review(seed):
    state = new_game(seed)
    rng = Random(seed ^ 0x574549)
    rows, actions = [], []
    while not state.ending:
        if state.phase == "day":
            view = public_state(state)
            rows += [f"## 第 {state.month} 月 · {view['chapter']}", "", view["event"]["description"], ""]
            rows += ["事件人物：" + view["event"]["npc_identity"], "目前疑點：" + view["event"]["current_question"]]
            rows.extend(c['text'] for c in view['event']['callbacks'])
            for char in view["characters"]:
                rows += [f"{char['name']}｜{char['role']}｜{char['status_label']}｜{char['actionable_label']}", char["thought"], "「" + char["dialogue"] + "」" if char["dialogue"] else "本月不在場。"]
            action = choose_day(state, "resource_guard_policy", rng)
            candidates = [a for a in legal_actions(state) if a[0]["id"] == PLANS[seed].get(state.month)]
            if candidates:
                action = max(candidates, key=lambda a: sum(state.character(cid).skills[a[0]["skill"]] for cid in a[1]))
            # At month 2 deliberately invite a publicly relevant background, even
            # when another disciple has a higher recommended ability.
            rationale = "依本局預定立場與公開資源安排。"
            if action and state.month == 2:
                option = action[0]
                hooks = {h["background"] for h in current_event(state).get("character_hooks", [])}
                candidates = [a for a in legal_actions(state) if a[0]["id"] == option["id"]
                              and any(state.character(cid).background["id"] in hooks for cid in a[1])]
                if candidates:
                    action = min(candidates, key=lambda a: sum(state.character(cid).skills[option["skill"]] for cid in a[1]))
                    rationale = "因公開背景與場景有關而邀其出勤；此處不以能力最高為唯一準則。"
            if action:
                option, team = action
                focus_id = choose_focus(state, "resource_guard_policy", rng, action)
                focus = next(f for f in view["investigations"] if f["id"] == focus_id)
                actions.append({"month": state.month, "phase": "day", "option": option["id"], "team": team, "focus_id": focus_id, "reason": rationale})
                rows += ["調查：" + focus["label"] + f"（成本 {focus['cost']}）"]
                rows += ["派遣：" + option["label"] + "／" + "、".join(state.character(cid).name for cid in team), rationale]
                resolve_day(state, option["id"], team, focus_id=focus_id)
            else:
                emergency_rest(state)
            rows += ["", "結果：", *state.last_result, ""]
            board = public_state(state)["evidence_board"]
            rows += ["證據板：" + "；".join(label + "：" + "、".join(e["title"] for e in board[key]) for key,label in (("confirmed","已證實"),("pending","待核實"),("claims","人物說法"),("excluded","排除事項")))]
        elif state.phase == "day_result":
            start_night(state)
        elif state.phase == "night":
            scene = night_view(state)
            rows += ["### 夜間 · " + scene["title"], "", scene["text"], ""]
            offered = [c for c in scene["choices"] if c["cost"] <= state.resources["treasury"]]
            choice = choose_night(state, "resource_guard_policy", rng)
            if scene["kind"] == "mainline_scene":
                choice = offered[0]["id"]
            elif scene["kind"] == "group_scene":
                choice = {0: "show_truth", 4: "keep_people", 6: "hold_gate"}[seed]
            elif scene["kind"] == "quiet_scene":
                choice = offered[0]["id"]
            label = next(c["label"] for c in offered if c["id"] == choice)
            rows += ["回應：" + label, ""]
            actions.append({"month": state.month, "phase": "night", "choice": choice})
            resolve_night(state, choice)
            rows += [*state.last_result, ""]
        elif state.phase == "deduction":
            view = checkpoint_view(state)
            selection = choose_deduction(state, "resource_guard_policy", rng)
            actions.append({"month":state.month,"phase":"deduction",**selection})
            rows += ["### 推理節點", view["question"], "可用證據：" + "、".join(e["title"] for e in view["evidence"])]
            resolve_deduction(state, **selection)
            rows += state.last_result
        else:
            begin_month(state)
    end = ending_view(state)
    rows += ["## 結局 · " + end["ending"], "", end["final_scene"], "", end["mystery_reveal"], *end["callbacks"], *end["personal_callbacks"], ""]
    rows += [c["name"] + "：" + c["epilogue"] for c in end["characters"]]
    # Hidden heart text is intentionally excluded from the reading transcript.
    return state, "\n\n".join(row for row in rows if row), actions


if __name__ == "__main__":
    output = Path(__file__).resolve().parent / "reports"
    output.mkdir(exist_ok=True)
    results = []
    for seed in PLANS:
        state, transcript, actions = run_review(seed)
        (output / f"reading_seed_{seed}.md").write_text(transcript, encoding="utf-8")
        results.append({"seed": seed, "thread": state.main_thread, "ending": state.ending, "month": state.month, "actions": actions})
    (output / "reading_actions.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    # Preserve three natural examples of each permanent consequence in the current version.
    cases = []
    for policy, kind in (("conservative_policy", "left"), ("conservative_policy", "defected"), ("random_policy", "dead")):
        found = 0
        for seed in range(250):
            for row in audit_outcomes(play_game(seed, policy)):
                if row["kind"] == kind:
                    cases.append({"policy": policy, **row})
                    found += 1
            if found >= 3:
                break
    (output / "fairness_audit.json").write_text(json.dumps(cases, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps([{k: v for k, v in r.items() if k != "actions"} for r in results], ensure_ascii=False))
