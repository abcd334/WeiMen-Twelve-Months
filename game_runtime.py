"""Keep Streamlit's rerun script and cached game imports on the same version."""
import importlib
import sys
from threading import Lock
from pathlib import Path


_reload_lock = Lock()
_MODULES = ("models", "case_models", "data_loader", "narrative", "case_engine", "investigation", "game_engine")
_sect_stamp = None
_SECT_MODULES = ("models", "sect_models", "sect_content", "sect_engine")


def load_current_engine(expected_version):
    """Refresh outdated dependencies before the UI binds any engine functions.

    Streamlit can rerun app.py while the process still holds earlier imports.
    Rebuild the dependency chain once on mismatch; ordinary reruns retain the
    same modules, data caches and current session. Existing games are not migrated.
    """
    if expected_version == "0.7":
        return load_sect_engine(expected_version)
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


def load_sect_engine(expected_version):
    """The open-ended simulation has a separate dependency graph from v0.6."""
    global _sect_stamp
    root = Path(__file__).resolve().parent
    stamp = tuple((root / (name + ".py")).stat().st_mtime_ns for name in _SECT_MODULES)
    try:
        engine = importlib.import_module("sect_engine")
    except ImportError:
        engine = None
    if engine is not None and getattr(engine, "GAME_VERSION", None) == expected_version and _sect_stamp in (None, stamp):
        _sect_stamp = stamp
        return engine
    with _reload_lock:
        importlib.invalidate_caches()
        for name in _SECT_MODULES:
            if name in sys.modules:
                importlib.reload(sys.modules[name])
            else:
                importlib.import_module(name)
        engine = sys.modules["sect_engine"]
        if engine.GAME_VERSION != expected_version:
            raise RuntimeError("遊戲程式尚未完成更新，請稍後重新整理頁面。")
        _sect_stamp = stamp
        return engine
