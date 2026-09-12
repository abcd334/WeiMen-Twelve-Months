"""v0.5: player-owned evidence, explicit deductions, and recoverable mistakes."""
from copy import deepcopy
from dataclasses import asdict
import json
from random import Random

import pytest

from data_loader import load_data, load_story_data, validate_story_data, validate_views
from game_engine import (InvalidAction, begin_month, current_event, ending_view, finish,
                         gain_intel, legal_actions, mystery_complete, new_game,
                         prepare_story_event, public_state, resolve_day, resolve_night, start_night)
from investigation import (checkpoint_view, evidence_board, investigation_options,
                           public_investigations, resolve_deduction, thread_for)
from simulate_balance import choose_day, choose_night, play_game


def digest(state):
    data = asdict(state)
    data['rng'] = state.rng.getstate()
    return data


def at_month(seed, month):
    state = new_game(seed)
    state.month, state.phase = month, 'day'
    scene = thread_for(state).get('monthly_scenes', {}).get(str(month), {})
    state.event_id = scene.get('event_id', 'inventory')
    prepare_story_event(state, current_event(state))
    return state


def investigate(state, focus, option_id=None):
    actions = legal_actions(state, focus)
    option, team = next((a for a in actions if a[0]['id'] == option_id), actions[0])
    resolve_day(state, option['id'], team, focus_id=focus)


@pytest.mark.parametrize('seed', (0, 4, 6))
def test_only_explicit_focus_can_award_core_evidence_across_entire_game(seed, monkeypatch):
    import game_engine
    monkeypatch.setattr(game_engine, 'mission_score', lambda *args: 100)
    state, rng = new_game(seed), Random(seed)
    for _ in range(70):
        if state.ending:
            break
        state.resources = dict.fromkeys(state.resources, 100)
        if state.phase == 'day':
            action = choose_day(state, 'highest_skill_policy', rng)
            resolve_day(state, action[0]['id'], action[1], focus_id='none')
        elif state.phase == 'day_result':
            start_night(state)
        elif state.phase == 'night':
            resolve_night(state, choose_night(state, 'highest_skill_policy', rng))
        elif state.phase == 'deduction':
            resolve_deduction(state, hypothesis='uncertain' if state.month == 4 else None)
        else:
            begin_month(state)
        assert not state.evidence
        assert not set(thread_for(state)['required_clues']) & state.intel.keys()
    assert state.month == 12 and state.ending
    assert not mystery_complete(state)
    assert thread_for(state)['ending_reveal'] not in ending_view(state)['mystery_reveal']


def test_selected_focus_gets_its_target_and_never_the_next_clue():
    state = at_month(4, 3)
    for char in state.characters:
        char.skills['medicine'] = 4
    investigate(state, 'inspect_ink')
    assert set(state.evidence) == {'card_ink'}  # Not original, which comes first in the graph.
    assert state.evidence['card_ink']['focus_id'] == 'inspect_ink'


def test_early_focus_does_not_reveal_second_card_before_month_three():
    for month in (1, 2):
        state = at_month(4, month)
        assert 'check_dates' not in {o['id'] for o in investigation_options(state)}
        investigate(state, 'inspect_ledger')
        assert set(state.evidence) == {'ledger_gap'}
        assert '兩張' not in state.evidence['ledger_gap']['text']


@pytest.mark.parametrize('option_id, acquired', [('verify_witness', True), ('accuse', False), ('archive', False)])
def test_witness_needs_verification_plan_even_with_high_skill(option_id, acquired, monkeypatch):
    import game_engine
    monkeypatch.setattr(game_engine, 'mission_score', lambda *args: -100)
    state = at_month(4, 5)
    for char in state.characters:
        char.skills['diplomacy'] = 5
    investigate(state, 'confront_witness', option_id)
    assert ('card_witness' in state.evidence) == acquired
    if not acquired:
        assert any(n['id'] == 'pending:card_witness' for n in state.leads)


@pytest.mark.parametrize('seed', (0, 4, 6))
def test_recovery_restores_every_missing_core_despite_mission_failure(seed, monkeypatch):
    import game_engine
    monkeypatch.setattr(game_engine, 'mission_score', lambda *args: -100)
    state = at_month(seed, 10)
    original = thread_for(state)['required_clues'][0]
    gain_intel(state, original, 'earlier verification')
    before = deepcopy(state.evidence[original])
    offered = {o['id']:o for o in investigation_options(state)}
    missing = set(thread_for(state)['required_clues']) - {original}
    assert set(offered['recover_chain']['targets']) == missing
    investigate(state, 'recover_chain')
    assert state.evidence[original] == before
    assert set(thread_for(state)['required_clues']) <= state.evidence.keys()
    assert all(state.evidence[cid]['focus_id'] == 'recover_chain' for cid in missing)
    assert not state.option_stats[-1]['success']
    assert not mystery_complete(state)


def test_failed_verification_keeps_known_evidence_and_pending_source_is_not_a_proof(monkeypatch):
    import game_engine
    monkeypatch.setattr(game_engine, 'mission_score', lambda *args: -100)
    state = at_month(4, 4)
    for char in state.characters:
        char.skills['medicine'] = 1
    gain_intel(state, 'card_original', 'earlier verification')
    before = deepcopy(state.evidence)
    investigate(state, 'inspect_ink')
    assert state.evidence == before and 'card_ink' not in state.intel
    pending = next(n for n in state.leads if n['id'] == 'pending:card_ink')
    assert '同批山外墨' not in pending['text']
    state.month, state.phase = 10, 'day'
    state.event_id = 'requisition'
    investigate(state, 'recover_card_ink')
    assert 'card_ink' in state.evidence
    assert not any(n['id'] == pending['id'] for n in state.leads)


def test_rechecking_known_proof_does_not_add_duplicate_or_pending_entry(monkeypatch):
    import game_engine
    monkeypatch.setattr(game_engine, 'mission_score', lambda *args: -100)
    state = at_month(4, 4)
    gain_intel(state, 'card_original', 'earlier verification')
    before = deepcopy(state.evidence)
    for char in state.characters:
        char.skills['strategy'] = 1
    investigate(state, 'inspect_seal')
    assert state.evidence == before and not state.leads


@pytest.mark.parametrize('seed', (0, 4, 6))
def test_all_missing_core_can_be_recovered_without_original_contact(seed):
    state = at_month(seed, 10)
    if state.main_thread == 'old_letters':
        state.character(state.story_flags['contact_character']).status = 'left'
    assert not state.evidence
    investigate(state, 'recover_chain')
    assert set(thread_for(state)['required_clues']) == set(state.evidence)


@pytest.mark.parametrize('focus', ('hear_external', 'follow_false_cards_internal'))
def test_external_contact_is_claim_or_lead_not_confirmed_betrayal(focus):
    state = at_month(4, 6)
    investigate(state, focus)
    assert not state.evidence and not state.intel
    assert len(state.claims if focus == 'hear_external' else state.leads) >= 1
    assert not state.major_outcomes
    assert all(c.status == 'active' for c in state.characters)


@pytest.mark.parametrize('month', (4, 8, 11))
def test_wrong_deduction_preserves_evidence_and_cannot_immediately_end_game(month):
    state = new_game(4)
    for cid in ('card_original', 'card_dates', 'card_witness', 'ink_source'):
        gain_intel(state, cid, 'earlier verification')
    before = deepcopy(state.evidence)
    state.month, state.phase = month, 'deduction'
    resources = dict(state.resources)
    selection = {4:{'hypothesis':'internal_theft'}, 8:{'evidence_ids':['card_dates','ink_source']},
                 11:{'evidence_ids':['card_original','card_dates','card_witness']}}[month]
    resolve_deduction(state, **selection)
    assert not state.ending and state.phase == 'deduction_result'
    assert state.evidence == before and not state.deduction_history[-1]['accepted']
    assert state.resources == {**resources, 'reputation':resources['reputation'] - 2}


@pytest.mark.parametrize('month', (8, 11))
def test_checkpoint_rejects_unacquired_claims_and_duplicates_atomically(month):
    state = new_game(4)
    gain_intel(state, 'card_original', 'verified')
    state.month, state.phase = month, 'deduction'
    view = checkpoint_view(state)
    assert [e['id'] for e in view['evidence']] == ['card_original']
    assert not {'correct_hypothesis','cross_pairs','required_clues','requires','supports','contradicts'} & view.keys()
    before = digest(state)
    for ids in (['card_original','card_ink'], ['false_cards_claim','card_original'], ['card_original']*2):
        with pytest.raises(InvalidAction):
            resolve_deduction(state, evidence_ids=ids)
        assert digest(state) == before


def test_correct_pair_opens_a_usable_followup_investigation():
    state = new_game(4)
    for cid in ('card_dates','cart_record'):
        gain_intel(state, cid, 'verified')
    state.month, state.phase = 8, 'deduction'
    resolve_deduction(state, evidence_ids=['cart_record','card_dates'])
    assert state.deduction_history[-1]['accepted']
    assert any(n['id'] == 'false_cards_cross_lead' for n in state.leads)
    begin_month(state)
    assert 'follow_cross_lead' in {f['id'] for f in public_investigations(state)}
    investigate(state, 'follow_cross_lead')
    assert 'card_witness' in state.evidence


@pytest.mark.parametrize('seed', (0, 4, 6))
def test_full_reveal_needs_acquired_core_and_player_assembled_chain(seed):
    state = new_game(seed)
    for cid in thread_for(state)['required_clues']:
        gain_intel(state, cid, 'verified')
    assert not mystery_complete(state)
    state.month, state.phase = 11, 'deduction'
    resolve_deduction(state, evidence_ids=thread_for(state)['required_clues'])
    assert mystery_complete(state)
    finish(state, '慘勝守山', 'Survival and case knowledge are separate.')
    assert ending_view(state)['mystery_reveal'] == thread_for(state)['ending_reveal']


def test_wrong_typed_chain_does_not_satisfy_final_reveal():
    state = new_game(4)
    for cid in thread_for(state)['required_clues']:
        gain_intel(state, cid, 'verified')
    state.month, state.phase = 11, 'deduction'
    resolve_deduction(state, evidence_ids=list(reversed(thread_for(state)['required_clues'])))
    assert not mystery_complete(state)


def test_deduction_rerun_stale_tokens_and_skip_cannot_mutate_game():
    state = new_game(4)
    state.month, state.phase = 4, 'night_result'
    before_resources = dict(state.resources)
    begin_month(state)
    assert state.phase == 'deduction' and state.month == 4 and state.resources == before_resources
    before = digest(state)
    with pytest.raises(InvalidAction):
        begin_month(state)
    with pytest.raises(InvalidAction):
        resolve_deduction(state, hypothesis='uncertain', token='8:deduction')
    assert digest(state) == before
    resolve_deduction(state, hypothesis='uncertain')
    assert state.deduction_history[-1]['accepted']
    before = digest(state)
    with pytest.raises(InvalidAction):
        resolve_deduction(state, hypothesis='uncertain')
    assert digest(state) == before
    begin_month(state)
    assert state.month == 5


def test_invalid_focus_and_combined_cost_are_validated_before_mutation():
    state = new_game(4)
    state.resources['treasury'] = 2
    before = digest(state)
    for focus in ('inspect_ink', 'not_offered', 'inspect_seal'):
        with pytest.raises(InvalidAction):
            resolve_day(state, 'pay', ['c0'], focus_id=focus)
        assert digest(state) == before


def test_board_separates_proof_claim_pending_and_refuted_hypothesis():
    state = at_month(4, 6)
    investigate(state, 'follow_false_cards_internal')
    gain_intel(state, 'card_original', 'verified')
    board = evidence_board(state)
    assert [n['id'] for n in board['confirmed']] == ['card_original']
    assert any(n['id'] == 'false_cards_internal' for n in board['pending'])
    assert board['claims'] and board['excluded']
    board['confirmed'].clear()
    assert state.evidence  # Projection is detached.


@pytest.mark.parametrize('seed', (0, 4, 6))
def test_dispatch_names_match_visible_characters_and_npcs_are_separate(seed):
    state = new_game(seed)
    view = public_state(state)
    visible = {c['id']:c['name'] for c in view['characters']}
    available = {c['id']:c['name'] for c in view['characters'] if c['actionable']}
    assert set(available) <= set(visible)
    npcs = load_story_data()['npcs']
    assert not {n['id'] for n in npcs} & visible.keys()
    assert not {n['name'] for n in npcs} & set(visible.values())
    assert all(cid in available for _, team in legal_actions(state) for cid in team)
    assert all(c['status_label'] and c['actionable_label'] and c['thought'] and c['dialogue'] for c in view['characters'])
    assert not view['event']['reactions']


@pytest.mark.parametrize('attributes,label', [({'fatigue':15},'稍有疲勞'), ({'fatigue':35},'疲憊'),
    ({'fatigue':65},'十分疲憊'), ({'injury':1},'輕傷'), ({'injury':2},'重傷休養'),
    ({'blocked_until':2},'暫停派遣'), ({'status':'left'},'離開門派'), ({'status':'defected'},'倒戈'), ({'status':'dead'},'死亡')])
def test_public_status_is_readable_without_raw_fatigue(attributes, label):
    state = new_game(4)
    char = state.characters[0]
    for key,value in attributes.items():
        setattr(char,key,value)
    view = public_state(state)['characters'][0]
    assert view['status_label'] == label and 'fatigue' not in view
    assert view['physical'] == label
    if not view['actionable']:
        assert all(char.id not in ids for _,ids in legal_actions(state))
    if char.status != 'active':
        assert not view['dialogue']


def test_case_schedule_views_and_graph_integrity():
    story = deepcopy(load_story_data())
    validate_story_data(story)
    assert len(load_data()[1]['events']) == 20
    for month in range(1,12):
        event = current_event(at_month(4, month))
        validate_views(event)
        assert not any(word in json.dumps(event['character_views'],ensure_ascii=False) for word in ('屍體', '手稿', '官府'))
    story['threads'][0]['recovery_paths'].pop()
    with pytest.raises(AssertionError, match='recovery path'):
        validate_story_data(story)


def test_authored_opinions_are_deterministic_and_do_not_expose_truth():
    state = new_game(4)
    before = digest(state)
    first = public_state(state)
    for _ in range(3):
        assert public_state(state) == first
    assert digest(state) == before
    forbidden = ('secret','trust','stress','betrayal_intent','correct_hypothesis','required_clues','cross_pairs')
    assert not any(key in json.dumps(first,ensure_ascii=False) for key in forbidden)
    assert '兩份爭議名帖使用同批山外墨' not in json.dumps(first,ensure_ascii=False)
    assert first['event']['current_question'] not in first['event']['description']


@pytest.mark.parametrize('seed', (0, 4, 6))
def test_same_seed_replays_every_investigation_and_deduction(seed):
    first = play_game(seed, 'highest_skill_policy')
    second = play_game(seed, 'highest_skill_policy')
    assert digest(first) == digest(second)
    assert [d['month'] for d in first.deduction_history] == [4,8,11]


def test_false_cards_earlier_investigation_returns_as_a_real_callback():
    state = play_game(4, 'highest_skill_policy')
    facts = {f['id']:f for f in state.facts}
    initial = next(e for e in state.evidence.values() if e['month'] <= 3)
    callback = next(c for c in state.callback_history if c['source_id'] == initial['fact_id'])
    assert initial['month'] < callback['month'] <= initial['month'] + 3
    assert facts[initial['fact_id']]['text'] in callback['text']
