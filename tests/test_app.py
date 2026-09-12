from pathlib import Path
from random import Random
import json

from streamlit.testing.v1 import AppTest
import pytest

from simulate_balance import choose_day, choose_night, choose_focus, choose_deduction

APP = Path(__file__).resolve().parents[1] / "app.py"


@pytest.mark.parametrize("seed", (0, 4, 6))
def test_streamlit_entire_game_reruns_and_feedback(tmp_path, monkeypatch, seed):
    import feedback
    monkeypatch.setattr(feedback, "DEFAULT_PATH", tmp_path / "survey.jsonl")
    at = AppTest.from_file(str(APP), default_timeout=10).run()
    assert not at.exception
    at.number_input(key="seed_input").set_value(seed).run()
    at.button(key="start").click().run()
    policy_rng = Random(seed ^ 0x574549)
    phases = set()
    for _ in range(70):
        assert not at.exception
        state = at.session_state["game"]
        phases.add(state.phase)
        if state.phase == "ended":
            break
        visible = " ".join(str(element.value) for group in (at.markdown, at.caption, at.info, at.warning, at.error) for element in group)
        for hidden in ("trust", "loyalty", "stress", "ambition", "goal_progress", "成功率", "信任 -", "壓力 +"):
            assert hidden not in visible
        if state.phase == "day":
            action = choose_day(state, "highest_skill_policy", policy_rng)
            if action is None:
                at.button(key="rest").click().run()
            else:
                option, team = action
                focus = choose_focus(state, "highest_skill_policy", policy_rng, action)
                at.radio(key=f"focus_{state.month}").set_value(focus).run()
                at.radio(key=f"plan_{state.month}").set_value(option["id"]).run()
                at.multiselect(key=f"team_{state.month}_{option['id']}").set_value(team).run()
                assert not at.button(key="confirm_day").disabled
                at.button(key="confirm_day").click().run()
        elif state.phase == "day_result":
            rng_before, resources_before = state.rng.getstate(), dict(state.resources)
            at.run()
            assert state.rng.getstate() == rng_before and state.resources == resources_before
            at.button(key="next_phase").click().run()
        elif state.phase == "night":
            response = choose_night(state, "highest_skill_policy", policy_rng)
            at.radio(key=f"night_{state.month}").set_value(response).run()
            at.button(key="confirm_night").click().run()
        elif state.phase == "deduction":
            selection = choose_deduction(state, "highest_skill_policy", policy_rng)
            if state.month == 4:
                at.radio(key="hypothesis_4").set_value(selection["hypothesis"]).run()
            elif not selection["evidence_ids"]:
                at.checkbox(key=f"deduction_defer_{state.month}").check().run()
            elif state.month == 8:
                at.multiselect(key="evidence_pair_8").set_value(selection["evidence_ids"]).run()
            else:
                for kind, cid in zip(("document", "physical", "witness"), selection["evidence_ids"]):
                    at.selectbox(key="chain_" + kind).set_value(cid).run()
            assert not at.button(key="confirm_deduction").disabled
            at.button(key="confirm_deduction").click().run()
        else:
            at.button(key="next_month").click().run()
    assert phases == {"day", "day_result", "night", "night_result", "deduction", "deduction_result", "ended"}
    assert state.month == 12 and state.ending
    assert not at.exception
    submit = next(button for button in at.button if button.label == "保存問卷")
    submit.click().run()
    assert not at.exception and (tmp_path / "survey.jsonl").exists()
    assert len((tmp_path / "survey.jsonl").read_text(encoding="utf-8").splitlines()) == 1
    assert json.loads((tmp_path / "survey.jsonl").read_text(encoding="utf-8"))["version"] == "0.5"


def test_streamlit_home_seed_change_and_restart():
    at = AppTest.from_file(str(APP), default_timeout=10).run()
    next(b for b in at.button if b.label == "隨機種子").click().run()
    assert 0 <= at.number_input(key="seed_input").value <= 2**32 - 1
    at.button(key="start").click().run()
    assert not at.exception
    next(b for b in at.button if b.label == "重新開始").click().run()
    assert not at.exception and at.button(key="start")


def test_dispatch_statuses_and_npc_identity_visible_before_selection():
    from game_engine import new_game
    from data_loader import load_story_data
    state = new_game(4)
    state.characters[0].injury = 2
    state.characters[1].blocked_until = 2
    state.characters[2].fatigue = 65
    at = AppTest.from_file(str(APP), default_timeout=10).run()
    at.session_state['game'] = state
    at.run()
    assert not at.exception
    visible = ' '.join(str(e.value) for group in (at.markdown, at.info, at.warning, at.caption) for e in group)
    assert '庫房管事・郭問舟' in visible and '商隊掌櫃・程守禾' in visible
    assert all('### ' + c.name in visible for c in state.characters)
    for label in ('重傷休養', '暫停派遣', '十分疲憊', '不可派遣', '可派遣'):
        assert label in visible
    assert at.radio(key='focus_1').value is None
    assert at.button(key='confirm_day').disabled
    selector = next(m for m in at.multiselect if m.key.startswith('team_'))
    assert len(selector.options) == 2
    assert all(c.name not in ' '.join(selector.options) for c in state.characters[:2])
    assert all(n['name'] not in ' '.join(selector.options) for n in load_story_data()['npcs'])
    assert all('｜' in label and '可派遣' in label for label in selector.options)
    # The initial screen has one character card per person; no second biography card below.
    assert len([m for m in at.markdown if str(m.value).startswith('### ')]) == 4


def test_previous_version_session_requires_explicit_new_game_without_inventing_evidence():
    from game_engine import new_game
    state = new_game(4)
    state.version = '0.4'
    state.intel['card_original'] = 'Legacy clue without a selected focus.'
    at = AppTest.from_file(str(APP), default_timeout=10).run()
    at.session_state['game'] = state
    at.run()
    assert not at.exception and not state.evidence
    assert any('重新選擇調查' in e.value for e in at.info)
    assert not at.radio
    next(b for b in at.button if b.label == '開始新版遊戲').click().run()
    assert not at.exception
    current = at.session_state['game']
    assert current.version == '0.5' and current.month == 1 and current.phase == 'day'
    assert current.seed == 4  # The hidden start-screen widget has been cleaned up.
    assert not current.evidence and 'card_original' not in current.intel
    assert at.radio(key='focus_1') and at.button(key='confirm_day')
    assert not any(b.key in ('start', 'start_current_version') for b in at.button)
    at.run()
    assert not at.exception and at.session_state['game'] is current


def test_upgrade_retains_previous_seed_when_home_widget_has_been_cleaned_up():
    from game_engine import new_game
    state = new_game(4)
    state.version = '0.4'
    at = AppTest.from_file(str(APP), default_timeout=10)
    at.session_state['game'] = state
    at.session_state['survey_saved'] = True
    at.session_state['response_id'] = 'previous-response'
    at.run()
    at.button(key='start_current_version').click().run()
    assert not at.exception
    assert at.session_state['game'].seed == 4
    assert at.session_state['game'].phase == 'day'
    assert 'survey_saved' not in at.session_state
    assert at.session_state['response_id'] != 'previous-response'
