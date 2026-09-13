"""Reproducible, agent-directed reading transcripts; not human playtest evidence."""
import json
from pathlib import Path
from random import Random

from game_engine import (begin_month, current_event, emergency_rest, ending_view,
                         legal_actions, new_game, night_view, public_state,
                         resolve_day, resolve_night, start_night)
from simulate_balance import audit_outcomes, choose_day, choose_night, choose_focus, choose_deduction, play_game
from investigation import checkpoint_view, resolve_deduction
from game_engine import resolve_case_action
from models import GAME_VERSION
import case_engine

PLANS = {
    0: {1: "ledger", 4: "investigate", 8: "watch"},
    4: {1: "ledger", 4: "appeal", 8: "open"},
    6: {1: "repair", 4: "investigate", 8: "watch"},
}

CASE_DAYS = {1:'compare_seal', 2:'check_workshop', 3:'compare_ink',
             5:'neutral_witness', 6:'compare_paper', 7:'ink_accounts',
             9:'public_reply', 10:'master_seal_record'}
CASE_PLANS = {
    'complete': dict(seed=4, days=CASE_DAYS, night='review'),
    'partial': dict(seed=4, days=CASE_DAYS, night='review', defer=True),
    'unresolved': dict(seed=4, night='hold', defer=True, days={
        1:'question_receiver', 2:'ask_driver', 3:'timeline', 5:'anonymous_witness',
        6:'compare_paper', 7:'follow_courier', 9:'public_reply', 10:'record_denial'}),
    'failure_recovery': dict(seed=0, days={**CASE_DAYS, 5:'public_witness', 10:'recover_missing'},
                             night='review', weak_month=5),
    'damaged': dict(seed=4, days=CASE_DAYS, night='publish'),
}


def run_review(seed, case_plan=None):
    state = new_game(seed, main_thread='false_cards' if case_plan else None)
    rng = Random(seed ^ 0x574549)
    rows, actions = [f'# 閱讀稿 v{GAME_VERSION} · seed {seed}'], []
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
            if case_plan:
                candidates = [(a, team) for a, team in case_engine.legal_case_actions(state)
                              if a.id == case_plan['days'][state.month]]
                choose = min if state.month == case_plan.get('weak_month') else max
                selected, team = choose(candidates, key=lambda row: sum(state.character(cid).skills[row[0].skill] for cid in row[1]))
                action = (next(a for a in view['case_actions'] if a['id'] == selected.id), team)
            # At month 2 deliberately invite a publicly relevant background, even
            # when another disciple has a higher recommended ability.
            rationale = "依本局預定立場與公開資源安排。"
            if case_plan and state.month == case_plan.get('weak_month'):
                rationale = '刻意派交涉能力較低的弟子公開查問，觀察自然失敗後的補證；未改動成功率或遊戲狀態。'
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
                if case_engine.is_case(state):
                    actions.append(dict(month=state.month, phase='day', action_id=option['id'], team=team, reason=rationale))
                    rows += ['案件行動：' + option['label'], '回答：' + option['question_part']]
                else:
                    focus_id = choose_focus(state, "resource_guard_policy", rng, action)
                    focus = next(f for f in view["investigations"] if f["id"] == focus_id)
                    actions.append({"month": state.month, "phase": "day", "option": option["id"], "team": team, "focus_id": focus_id, "reason": rationale})
                    rows += ["調查：" + focus["label"] + f"（成本 {focus['cost']}）"]
                rows += ["派遣：" + option["label"] + "／" + "、".join(state.character(cid).name for cid in team), rationale]
                if case_engine.is_case(state):
                    resolve_case_action(state, option['id'], team)
                else:
                    resolve_day(state, option["id"], team, focus_id=focus_id)
            else:
                actions.append(dict(month=state.month, phase='day', action_id='rest'))
                emergency_rest(state)
            rows += ["", "結果：", *state.last_result, ""]
            board = public_state(state)["evidence_board"]
            rows += ["證據板：" + "；".join(label + "：" + "、".join(e["title"] for e in board[key]) for key,label in (("confirmed","已證實"),("pending","待核實"),("claims","人物說法"),("excluded","排除事項")))]
            if case_engine.is_case(state):
                rows += ['本日來源：' + '、'.join(state.day_context['fact_ids']),
                         '新證據：' + '、'.join(state.day_context['evidence_gained'])]
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
            if case_plan:
                choice = 'keep_people' if state.month == 11 else case_plan['night']
            label = next(c["label"] for c in offered if c["id"] == choice)
            rows += ["回應：" + label, ""]
            actions.append({"month": state.month, "phase": "night", "choice": choice})
            resolve_night(state, choice)
            rows += [*state.last_result, ""]
        elif state.phase == "deduction":
            if case_engine.is_case(state):
                v = public_state(state)
                rows += [f"## 第 {state.month} 月 · {v['event']['title']}", v['event']['description']]
                rows.extend(c['text'] for c in v['event']['callbacks'])
            view = checkpoint_view(state)
            selection = choose_deduction(state, "resource_guard_policy", rng)
            if case_plan and case_plan.get('defer'):
                selection = dict(hypothesis='uncertain') if state.month == 4 else dict(evidence_ids=[])
            actions.append({"month":state.month,"phase":"deduction",**selection})
            rows += ["### 推理節點", view["question"], "可用證據：" + "、".join(e["title"] for e in view["evidence"])]
            resolve_deduction(state, **selection)
            rows += state.last_result
        elif state.phase == 'deduction_result' and case_engine.is_case(state):
            start_night(state)
        else:
            begin_month(state)
    end = ending_view(state)
    if case_engine.is_case(state):
        rows += [f"案件軸：{end['mystery_axis']}；門派軸：{end['sect_axis']}", end['reason']]
    rows += ["## 結局 · " + end["ending"], "", end["final_scene"], "", end["mystery_reveal"], *end["callbacks"], *end["personal_callbacks"], ""]
    rows += [c["name"] + "：" + c["epilogue"] for c in end["characters"]]
    # Hidden heart text is intentionally excluded from the reading transcript.
    return state, "\n\n".join(row for row in rows if row), actions


def replay_case(seed, actions):
    """Replay recorded inputs without running a policy or looking up answers."""
    state = new_game(seed, main_thread='false_cards')
    for row in actions:
        while state.phase in ('day_result', 'deduction_result', 'night_result'):
            if state.phase == 'night_result':
                begin_month(state)
            else:
                start_night(state)
        assert (state.month, state.phase) == (row['month'], row['phase'])
        if row['phase'] == 'day':
            if row['action_id'] == 'rest':
                emergency_rest(state)
            else:
                resolve_case_action(state, row['action_id'], row['team'])
        elif row['phase'] == 'night':
            resolve_night(state, row['choice'])
        else:
            resolve_deduction(state, **{k:row[k] for k in ('hypothesis','evidence_ids') if k in row})
    if state.phase == 'night_result':
        begin_month(state)
    return state


if __name__ == "__main__":
    output = Path(__file__).resolve().parent / "reports" / ('v' + GAME_VERSION)
    output.mkdir(exist_ok=True, parents=True)
    results = []
    for seed in PLANS:
        state, transcript, actions = run_review(seed)
        (output / f"reading_seed_{seed}.md").write_text(transcript, encoding="utf-8")
        results.append({"version": GAME_VERSION, "action_schema": 'case_v1' if case_engine.is_case(state) else 'legacy_v05', "seed": seed, "thread": state.main_thread, "ending": state.ending, "month": state.month, "actions": actions})
    for name, plan in CASE_PLANS.items():
        state, transcript, actions = run_review(plan['seed'], plan)
        replay = replay_case(plan['seed'], actions)
        assert replay.case_history == state.case_history and replay.rng.getstate() == state.rng.getstate()
        assert replay.ending == state.ending and replay.resources == state.resources
        (output / f'reading_case_{name}.md').write_text(transcript, encoding='utf-8')
        results.append(dict(version=GAME_VERSION, action_schema='case_v1', branch=name, seed=plan['seed'],
            thread=state.main_thread, ending=state.ending, month=state.month, actions=actions,
            mystery_axis=state.mystery_axis, sect_axis=state.sect_axis, replay_verified=True))
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
