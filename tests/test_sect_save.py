import json

import pytest

import sect_engine as engine
from sect_save import export_save, import_save
from review_sect import choose_plan


@pytest.mark.parametrize("turns,phase", [(0, "planning"), (1, "result"), (24, "planning"), (38, "result")])
def test_save_roundtrip_keeps_state_rng_and_next_action(turns, phase):
    original = engine.new_game(4)
    for index in range(turns):
        action, team, jobs = choose_plan(original, "focus")
        engine.resolve_turn(original, action, team, jobs)
        if index < turns - 1 or phase == "planning":
            engine.next_tick(original)
    loaded = import_save(export_save(original))
    assert engine.public_state(loaded) == engine.public_state(original)
    assert loaded.rng.getstate() == original.rng.getstate()
    for state in (original, loaded):
        if state.phase == "result":
            engine.next_tick(state)
        action, team, jobs = choose_plan(state, "focus")
        engine.resolve_turn(state, action, team, jobs)
    assert engine.public_state(loaded) == engine.public_state(original)


@pytest.mark.parametrize("payload", [b"{}", b"[]", b"null", b"bad json", b"\xff", b"[" * 2000, b"x" * (4 * 1024 * 1024 + 1)],
                         ids=["empty", "array", "null", "invalid-json", "encoding", "nested", "oversized"])
def test_malformed_or_oversized_save_is_rejected(payload):
    with pytest.raises(ValueError):
        import_save(payload)


def test_edited_or_different_version_save_fails_closed():
    original = engine.new_game(4)
    before = engine.public_state(original)
    saved = json.loads(export_save(original))
    saved["version"] = "0.6"
    with pytest.raises(ValueError):
        import_save(json.dumps(saved).encode())
    saved["version"] = "0.7"
    saved["fingerprint"] = "wrong"
    with pytest.raises(ValueError):
        import_save(json.dumps(saved).encode())
    assert engine.public_state(original) == before


def test_ended_game_can_be_loaded_but_not_advanced():
    state = engine.new_game(4)
    while state.phase != "ended":
        engine.resolve_turn(state, "rest", [c.id for c in state.active()])
        if state.phase == "result":
            engine.next_tick(state)
    restored = import_save(export_save(state))
    assert restored.phase == "ended" and restored.ending == state.ending
    with pytest.raises(engine.InvalidAction):
        engine.next_tick(restored)
