"""Versioned JSON action replays. Never deserialize executable Python objects."""
import hashlib
import json

import sect_engine as engine

FORMAT = "weimen-history-v1"
MAX_DECISIONS = 1000
MAX_BYTES = 4 * 1024 * 1024


def fingerprint(state):
    payload = json.dumps(engine.public_state(state), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def export_save(state):
    if len(state.decisions) > MAX_DECISIONS:
        raise ValueError("此存檔格式最多支援 1000 旬。")
    data = dict(format=FORMAT, version=state.version, seed=state.seed, phase=state.phase,
        decisions=[dict(action=d["action_id"], team=d["participants"], jobs=d["assignments"]) for d in state.decisions],
        fingerprint=fingerprint(state))
    return json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")


def import_save(payload):
    if not isinstance(payload, bytes) or len(payload) > MAX_BYTES:
        raise ValueError("存檔需為不超過 4 MB 的 JSON 檔案。")
    try:
        data = json.loads(payload.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError("無法讀取這份 JSON 存檔。") from exc
    if not isinstance(data, dict) or set(data) != {"format", "version", "seed", "phase", "decisions", "fingerprint"}:
        raise ValueError("存檔欄位不完整或格式不符。")
    if data["format"] != FORMAT or data["version"] != engine.GAME_VERSION:
        raise ValueError("這份存檔不屬於目前的 v0.7 版本。")
    decisions = data["decisions"]
    if not isinstance(decisions, list) or len(decisions) > MAX_DECISIONS or data["phase"] not in ("planning", "result", "ended"):
        raise ValueError("存檔進度不正確。")
    current = engine.new_game(data["seed"])
    try:
        for index, decision in enumerate(decisions):
            if not isinstance(decision, dict) or set(decision) != {"action", "team", "jobs"}:
                raise ValueError("存檔中有不完整的行動。")
            if not isinstance(decision["action"], str) or not isinstance(decision["jobs"], dict):
                raise ValueError("存檔中的行動格式不正確。")
            engine.resolve_turn(current, decision["action"], decision["team"], decision["jobs"])
            if index < len(decisions) - 1 or data["phase"] == "planning":
                engine.next_tick(current)
    except (engine.InvalidAction, TypeError, KeyError) as exc:
        raise ValueError("這份存檔的行動無法依目前規則重播，原本進度未被更動。") from exc
    if current.phase != data["phase"] or fingerprint(current) != data["fingerprint"]:
        raise ValueError("重播結果與存檔不一致；可能曾改動檔案，或存檔使用不同修訂的規則。")
    return current
