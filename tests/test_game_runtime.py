"""Exercise cached old imports in a subprocess so other tests keep their classes."""
import os
from pathlib import Path
import subprocess
import sys

import game_engine
from game_runtime import load_current_engine


def test_current_runtime_does_not_reload_or_mutate_existing_game(monkeypatch):
    import game_runtime
    state = game_engine.new_game(4)
    before = state.rng.getstate()
    monkeypatch.setattr(game_runtime.importlib, 'reload', lambda module: (_ for _ in ()).throw(AssertionError('Unexpected reload')))
    assert load_current_engine('0.5') is game_engine
    assert state.rng.getstate() == before and state.month == 1


def test_cached_old_engine_is_refreshed_before_starting_or_upgrading():
    code = r'''
from dataclasses import dataclass
import sys
import types
from streamlit.testing.v1 import AppTest

# Simulate old module objects held by a long-running Streamlit process. These
# intentionally lack the v0.5 API, so reloading only the version string fails.
for name in ('models', 'data_loader', 'narrative', 'investigation', 'game_engine'):
    module = types.ModuleType(name)
    module.__file__ = name + '.py'
    sys.modules[name] = module

@dataclass
class LegacyGame:
    seed: int
    version: str = '0.4'

sys.modules['game_engine'].new_game = LegacyGame
at = AppTest.from_file('app.py', default_timeout=10).run()
assert not at.exception
at.number_input(key='seed_input').set_value(4).run()
at.button(key='start').click().run()
assert not at.exception
state = at.session_state['game']
assert state.version == '0.5' and state.month == 1 and state.phase == 'day'
assert state.seed == 4 and state.main_thread == 'false_cards'
assert at.radio(key='focus_1')
assert not any(b.key in ('start', 'start_current_version') for b in at.button)

# The first dispatch must use the refreshed engine and evidence rules too.
at.radio(key='focus_1').set_value('inspect_seal').run()
at.radio(key='plan_1').set_value('ledger').run()
at.multiselect(key='team_1_ledger').set_value(['c1']).run()
at.button(key='confirm_day').click().run()
assert not at.exception and state.phase == 'day_result'
assert 'card_original' in state.evidence
at.run()
assert not at.exception and at.session_state['game'] is state

# A previously saved legacy session is left alone until explicitly restarted.
at.session_state['game'] = LegacyGame(4)
at.run()
assert not at.exception and at.button(key='start_current_version')
at.button(key='start_current_version').click().run()
assert not at.exception
current = at.session_state['game']
assert current.version == '0.5' and current.phase == 'day' and current.month == 1
assert not current.evidence
at.run()
assert not at.exception and at.session_state['game'] is current
'''
    result = subprocess.run([sys.executable, '-c', code], cwd=Path(__file__).resolve().parents[1],
                            env={**os.environ, 'PYTHONIOENCODING':'utf-8'},
                            capture_output=True, text=True, encoding='utf-8', timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
