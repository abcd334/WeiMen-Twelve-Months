"""Keep Streamlit's rerun script and cached game imports on the same version."""
import importlib
import sys
from threading import Lock


_reload_lock = Lock()
_MODULES = ("models", "case_models", "data_loader", "narrative", "case_engine", "investigation", "game_engine")


def load_current_engine(expected_version):
    """Refresh outdated dependencies before the UI binds any engine functions.

    Streamlit can rerun app.py while the process still holds earlier imports.
    Rebuild the dependency chain once on mismatch; ordinary reruns retain the
    same modules, data caches and current session. Existing games are not migrated.
    """
    engine = importlib.import_module("game_engine")
    if getattr(engine, "GAME_VERSION", None) == expected_version:
        return engine
    with _reload_lock:
        if getattr(engine, "GAME_VERSION", None) != expected_version:
            importlib.invalidate_caches()
            for name in _MODULES:
                if name in sys.modules:
                    importlib.reload(sys.modules[name])
                else:
                    importlib.import_module(name)
            engine = sys.modules["game_engine"]
            if getattr(engine, "GAME_VERSION", None) != expected_version:
                raise RuntimeError("遊戲程式尚未完成更新，請稍後重新整理頁面。")
    return engine
