"""The launcher itself can remain cached across a Streamlit Cloud deployment."""
import os
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.parametrize("saved_game", [False, True])
def test_cached_v06_launcher_can_boot_v07_without_restarting_server(saved_game):
    code = r'''
from pathlib import Path
import sys
import types
from streamlit.testing.v1 import AppTest
import game_engine

# Use the real v0.6 launcher, not just a stubbed engine. Its dependency list
# cannot discover sect_engine, even after it reloads every module it knows.
legacy = types.ModuleType('game_runtime')
legacy.__file__ = str(Path('game_runtime.py').resolve())
source = Path('tests/runtime_v06_fixture.txt').read_text(encoding='utf-8-sig')
exec(compile(source, legacy.__file__, 'exec'), legacy.__dict__)
sys.modules['game_runtime'] = legacy
assert not hasattr(legacy, 'load_sect_engine')

at = AppTest.from_file('app.py', default_timeout=10)
saved = game_engine.new_game(4) if SAVED_GAME else None
if saved:
    at.session_state['game'] = saved
at.run()
assert not at.exception
assert not at.error, [e.value for e in at.error]
if saved:
    assert at.session_state['game'] is saved
at.button(key='start_current_version' if saved else 'start').click().run()
assert not at.exception and not at.error
state = at.session_state['game']
assert state.version == '0.7' and len(state.characters) == 6
if saved:
    assert state.seed == 4
at.selectbox(key='action_1').set_value('work').run()
at.multiselect(key='team_1_work').set_value(['c0', 'c1']).run()
at.button(key='confirm_turn').click().run()
assert not at.exception and state.phase == 'result'
before = state.rng.getstate(), dict(state.resources)
import game_runtime
runtime_loader = game_runtime.load_current_engine
at.run()
assert not at.exception and at.session_state['game'] is state
assert (state.rng.getstate(), state.resources) == before
assert game_runtime.load_current_engine is runtime_loader
'''.replace('SAVED_GAME', repr(saved_game))
    result = subprocess.run([sys.executable, '-c', code], cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, 'PYTHONIOENCODING': 'utf-8', 'PYTHONDONTWRITEBYTECODE': '1'},
        capture_output=True, text=True, encoding='utf-8', timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
