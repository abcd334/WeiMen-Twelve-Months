from pathlib import Path
from streamlit.testing.v1 import AppTest

import sect_engine as engine

APP = Path(__file__).resolve().parents[1] / "app.py"


def test_new_ui_can_play_24_decisions_review_and_continue(tmp_path, monkeypatch):
    import sect_feedback
    monkeypatch.setattr(sect_feedback, "DEFAULT_PATH", tmp_path / "feedback.jsonl")
    at = AppTest.from_file(str(APP), default_timeout=15).run()
    assert not at.exception
    at.number_input(key="seed_input").set_value(4).run()
    at.button(key="start").click().run()
    assert not at.exception
    for tick in range(1, 25):
        state = at.session_state["game"]
        assert state.tick == tick and len(state.characters) == 6
        assert at.button(key="confirm_turn").disabled
        at.selectbox(key=f"action_{tick}").set_value("work").run()
        at.multiselect(key=f"team_{tick}_work").set_value(["c0", "c1"]).run()
        assert not at.exception and not at.button(key="confirm_turn").disabled
        at.button(key="confirm_turn").click().run()
        assert not at.exception and state.phase == "result"
        before = (state.rng.getstate(), dict(state.resources), len(state.decisions))
        at.run()
        assert before == (state.rng.getstate(), dict(state.resources), len(state.decisions))
        if tick < 24:
            at.button(key="next_tick").click().run()
    assert at.text_area(key="reason")
    at.text_area(key="reason").set_value("唐見川與同門一起做工補上糧餉，後來又提起這件事。")
    next(b for b in at.button if b.label == "保存這局的感受").click().run()
    assert not at.exception and at.session_state["survey_saved"]
    assert (tmp_path / "feedback.jsonl").exists()
    at.button(key="next_tick").click().run()
    assert not at.exception and at.session_state["game"].tick == 25
    text = " ".join(str(e.value) for group in (at.markdown, at.caption, at.info, at.warning) for e in group)
    assert "敘事權重" not in text and "證據板" not in text and "夜談" not in text


def test_old_session_requires_explicit_restart_with_original_seed():
    from game_engine import new_game
    legacy = new_game(6)
    at = AppTest.from_file(str(APP), default_timeout=10)
    at.session_state["game"] = legacy
    at.run()
    assert not at.exception and at.session_state["game"] is legacy
    at.button(key="start_current_version").click().run()
    assert not at.exception
    state = at.session_state["game"]
    assert state.version == "0.7" and state.seed == 6 and state.tick == 1
    assert len(state.characters) == 6


def test_personal_memory_has_required_people_and_ui_shows_source():
    state = engine.new_game(4)
    engine.resolve_turn(state, "train", ["c0", "c1"])
    for _ in range(3):
        engine.next_tick(state)
        engine.resolve_turn(state, "work", ["c2", "c3"])
    engine.next_tick(state)
    action = next(a for a in engine.available_actions(state) if a.get("event_id") == "memory_return")
    at = AppTest.from_file(str(APP), default_timeout=10)
    at.session_state["game"] = state
    at.run()
    at.selectbox(key=f"action_{state.tick}").set_value(action["id"]).run()
    selector = at.multiselect(key=f"team_{state.tick}_{action['id']}")
    assert selector.disabled and selector.value == action["required"]
    assert any("源於第 1 年 1 月上旬" in str(e.value) for e in at.markdown)
    at.button(key="confirm_turn").click().run()
    assert not at.exception and state.callback_history


def test_all_injured_still_have_a_rest_path():
    state = engine.new_game(4)
    for c in state.characters:
        c.injury = 2
    at = AppTest.from_file(str(APP), default_timeout=10)
    at.session_state["game"] = state
    at.run()
    at.selectbox(key="action_1").set_value("rest").run()
    at.multiselect(key="team_1_rest").set_value([c.id for c in state.characters]).run()
    at.button(key="confirm_turn").click().run()
    assert not at.exception and state.phase == "result"
