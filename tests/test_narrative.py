from copy import deepcopy
import json
import pytest

from game_engine import new_game, public_state, public_character_context
from narrative import render_event_opening, render_assignment_preview
from data_loader import load_data, load_story_data, validate_data
from game_engine import (begin_month, build_night_scene, current_event, current_thread, ending_view,
                         finish, gain_intel, legal_actions, mystery_complete, night_view,
                         observe_character, prepare_story_event, qualifying_warnings,
                         resolve_day, resolve_night, start_night)
from simulate_balance import POLICIES, play_game
from audit_narrative import audit_game, NIGHT_TYPES
from investigation import resolve_deduction


@pytest.mark.parametrize("policy", POLICIES)
def test_story_coverage_across_actions_and_seeds(policy):
    for seed in range(25):
        state = play_game(seed, policy)
        audit = audit_game(state)
        if state.month == 12:
            assert audit["callbacks_2_to_10"] >= 3
            assert all(n >= 2 for n in audit["spotlights_before_10"].values())
            assert audit["scene_counts"].get("relationship_scene", 0) >= 2
            assert audit["scene_counts"].get("mainline_scene", 0) >= 2
            assert audit["scene_counts"].get("quiet_scene", 0) <= 2
            assert audit["group_complete"]
            assert audit["ending_callback_count"] >= 2
            assert {"setup", "escalation", "payoff"} <= set(audit["beats"])
            assert 150 <= audit["final_scene_length"] <= 300
            assert all(80 <= n <= 180 for n in audit["epilogue_lengths"])
            days = [s for s in state.scene_history if s["type"] == "day"]
            assert sum(s["related"] for s in days if 5 <= s["month"] <= 7) >= 2
        if any(s.get("scene_id") == "suspicion" for s in state.scene_history):
            assert audit["month8_grounded"]
        nights = [s for s in state.scene_history if s["type"] in NIGHT_TYPES]
        for a, b, c in zip(nights, nights[1:], nights[2:]):
            if len(state.active()) > 1:
                assert not (len(a["speakers"]) == 1 and a["speakers"] == b["speakers"] == c["speakers"])
        facts = {f["id"]: f for f in state.facts}
        for callback in state.callback_history:
            source = facts[callback["source_id"]]
            assert source["month"] < callback["month"]
            if callback["text"].startswith("第 "):
                assert callback["month"] - source["month"] <= 3


@pytest.mark.parametrize("seed", (0, 4, 6))
def test_full_narrative_and_choice_replay_is_deterministic(seed):
    first, second = (play_game(seed, "resource_guard_policy") for _ in range(2))
    assert first.scene_history == second.scene_history
    assert first.callback_history == second.callback_history
    assert ending_view(first) == ending_view(second)


def test_observations_only_record_changes_without_repeating_monthly():
    state = new_game(6)
    char = state.characters[0]
    char.secret = {"id": "none"}
    char.stress, char.fatigue, char.trust = 55, 0, 55
    observe_character(state, char)
    first = deepcopy(state.observations)
    when = char.recent_month
    for month in (2, 3, 4):
        state.month = month
        observe_character(state, char)
    assert state.observations == first and char.recent_month == when
    char.stress, char.trust = 0, 35
    observe_character(state, char)
    assert len(state.observations) == len(first) + 1
    assert state.observations[-1].text != first[-1].text


def test_two_distinct_prior_month_warnings_survive_deduplication():
    state = new_game(0)
    char = state.characters[0]
    char.secret = {"id": "contact"}
    char.choices = ["discipline", "discipline"]
    char.trust, char.loyalty, char.stress = 20, 30, 80
    observe_character(state, char)
    observe_character(state, char)
    state.month = 2
    observe_character(state, char)
    assert not qualifying_warnings(state, char, "betrayal")
    state.month = 3
    warnings = qualifying_warnings(state, char, "betrayal")
    assert len(warnings) == 2 and len({c.text for c in warnings}) == 2
    observe_character(state, char)
    assert len([c for c in state.observations if c.character_id == char.id]) == 2


def test_public_character_history_removes_repeated_recent_and_old_month_prefixes():
    char = new_game(1).characters[0]
    char.recent = "第 3 月：收到了需要查證的回信。"
    char.experiences = ["第 1 月：同門曾協助核帳。", "第 2 月：同門曾協助核帳。", char.recent]
    assert char.public(3)["experiences"] == ["第 2 月：同門曾協助核帳。"]


@pytest.mark.parametrize("seed", (0, 4, 6))
def test_mystery_needs_correlated_core_clues_and_preview_stays_private(seed):
    state = new_game(seed)
    thread = current_thread(state)
    for clue in ("pattern", "supply", "letters"):
        if clue in load_data()[1]["intel"]:
            gain_intel(state, clue, "test")
    assert not mystery_complete(state)
    for clue in thread["required_clues"][:-1]:
        gain_intel(state, clue, "test")
    assert not mystery_complete(state)
    option, team = legal_actions(state)[0]
    resolve_day(state, option["id"], team)
    start_night(state)
    rng = state.rng.getstate()
    view = night_view(state)
    assert thread["ending_reveal"] not in json.dumps(view, ensure_ascii=False)
    assert not {"psych", "secret", "effects", "reaction", "grant_thread_clue"} & view["choices"][0].keys()
    assert state.rng.getstate() == rng and view == night_view(state)
    finish(state, "慘勝守山", "test")
    assert thread["ending_reveal"] not in ending_view(state)["mystery_reveal"]
    gain_intel(state, thread["required_clues"][-1], "test")
    assert not mystery_complete(state)  # Acquisition alone no longer assembles the chain.
    state.month, state.phase = 11, "deduction"
    resolve_deduction(state, evidence_ids=thread["required_clues"])
    assert mystery_complete(state)
    assert ending_view(state)["mystery_reveal"] == thread["ending_reveal"]


def test_restricting_contact_blocks_new_letter_from_both_day_and_night():
    state = new_game(0)
    assert state.main_thread == "old_letters"
    contact = state.character(state.story_flags["contact_character"])
    state.month = 8
    state.event_id = "suspicion"
    prepare_story_event(state, current_event(state))
    resolve_day(state, "restrict", [contact.id], focus_id="verify_reply")
    assert contact.blocked_until == 9
    assert any(contact.name in text and "工作由誰接" in text for text in state.last_result)
    before = dict(state.intel)
    assert "letter_reply" not in state.evidence
    assert any("聯絡管道" in n["text"] for n in state.leads)
    state.phase = "night"
    state.night_character = contact.id
    state.night_scene = build_night_scene(state, "mainline_scene", [contact, next(c for c in state.active() if c != contact)])
    resolve_night(state, state.night_scene["choices"][0]["id"])
    assert state.intel == before
    assert not state.evidence  # Night talks cannot silently award a case clue.


def test_successful_pair_mission_still_shows_conflict_and_both_characters():
    state = new_game(8)
    first, second = state.characters[:2]
    first.relationships[second.id]["value"] = -30
    second.relationships[first.id]["value"] = -30
    option = next(o for o in current_event(state)["options"] if o["count"] == 2)
    resolve_day(state, option["id"], [first.id, second.id])
    text = "\n".join(state.last_result)
    assert first.name in text and second.name in text and "下次改分工前" in text


def test_relationship_choices_change_both_people_and_partner_speaks():
    state = new_game(7)
    state.month, state.phase = 2, "day_result"
    start_night(state)
    first, second = [state.character(cid) for cid in state.night_scene["speakers"]]
    assert first.name in night_view(state)["text"] and second.name in night_view(state)["text"]
    before = (first.trust, second.trust)
    choice = next(c for c in state.night_scene["choices"] if c.get("approach") == "support")
    resolve_night(state, choice["id"])
    assert first.trust != before[0] and second.trust != before[1]
    assert first.history[-1]["text"] == second.history[-1]["text"]


def test_group_remembers_absent_person_and_final_choice_does_not_set_ending():
    state = new_game(6)
    state.month, state.phase = 11, "day_result"
    absent = state.characters[-1]
    absent.status = "dead"
    start_night(state)
    text = night_view(state)["text"]
    assert "空碗" in text and absent.name in text
    assert all(c.name in text for c in state.active())
    resources = dict(state.resources)
    resolve_night(state, "show_truth")
    assert state.resources == resources and state.ending == ""


def test_generic_placeholders_and_shallow_variants_are_rejected():
    chars, missions, personal = deepcopy(load_data())
    missions["events"][0]["options"][0]["success_narratives"][0] = "有了進展" * 20
    with pytest.raises(AssertionError, match="placeholder"):
        validate_data(chars, missions, personal)
    chars, missions, personal = load_data()
    for event in missions["events"]:
        for option in event["options"]:
            for key in ("success_narratives", "failure_narratives"):
                # Reordering identical characters was the previous shallow variant bug.
                assert sorted(option[key][0]) != sorted(option[key][1])
    assert len({tuple(a["resolutions"].values()) for a in personal["arcs"]}) == 6


def test_public_narrative_context_is_deterministic_and_does_not_mutate():
    a, b = new_game(42), new_game(42)
    before = deepcopy(a.event_context)
    rng = a.rng.getstate()
    assert a.main_thread == b.main_thread
    assert render_event_opening(a.event_context) == render_event_opening(b.event_context)
    assert a.event_context == before and a.rng.getstate() == rng


def test_assignment_context_cannot_leak_secret_or_thread_truth():
    state = new_game(10)
    char = state.characters[0]
    char.secret = {"id": "SECRET_SENTINEL", "text": "UNREVEALED_SENTINEL"}
    context = public_character_context(state, char)
    assert not {"secret", "trust", "stress", "relationships", "fear"} & context.keys()
    lines = render_assignment_preview(state.event_context, [context])
    assert "SENTINEL" not in str(lines)
    assert "ending_reveal" not in str(public_state(state))


def test_phase_two_full_twelve_month_run():
    from simulate_balance import play_game
    state = play_game(42, "resource_guard_policy")
    assert state.month == 12
    assert any(s["type"] == "group_scene" and s["month"] == 11 for s in state.scene_history)
    assert {b["beat"] for b in state.thread_beats} == {"setup", "escalation", "payoff"}
    for row in state.scene_history:
        if row.get("scene_id") == "suspicion":
            assert len(row["evidence_ids"]) >= 2
