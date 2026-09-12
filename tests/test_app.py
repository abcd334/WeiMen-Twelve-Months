from pathlib import Path
from random import Random
import json

from streamlit.testing.v1 import AppTest
import pytest

from simulate_balance import choose_day, choose_night

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
    for _ in range(60):
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
        else:
            at.button(key="next_month").click().run()
    assert phases == {"day", "day_result", "night", "night_result", "ended"}
    assert state.month == 12 and state.ending
    assert not at.exception
    submit = next(button for button in at.button if button.label == "保存問卷")
    submit.click().run()
    assert not at.exception and (tmp_path / "survey.jsonl").exists()
    assert len((tmp_path / "survey.jsonl").read_text(encoding="utf-8").splitlines()) == 1
    assert json.loads((tmp_path / "survey.jsonl").read_text(encoding="utf-8"))["version"] == "0.4"


def test_streamlit_home_seed_change_and_restart():
    at = AppTest.from_file(str(APP), default_timeout=10).run()
    next(b for b in at.button if b.label == "隨機種子").click().run()
    assert 0 <= at.number_input(key="seed_input").value <= 2**32 - 1
    at.button(key="start").click().run()
    assert not at.exception
    next(b for b in at.button if b.label == "重新開始").click().run()
    assert not at.exception and at.button(key="start")
