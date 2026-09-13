"""Local qualitative feedback after 24 decisions; independent of game RNG."""
import json
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parent / "feedback" / "v07_responses.jsonl"


def save_feedback(state, memorable, reason, replay, response_id, path=None):
    if len(state.decisions) < 24 and state.phase != "ended":
        raise ValueError("完成 24 次決策後再回看這一局。")
    if memorable not in [c.name for c in state.characters] + ["沒有特別記得的人"]:
        raise ValueError("請選擇本局門人。")
    if not reason.strip() or len(reason) > 2000 or replay not in ("可能很不一樣", "也許", "感覺差不多"):
        raise ValueError("請寫下原因並選擇重玩感受。")
    if not isinstance(response_id, str) or not response_id or len(response_id) > 100:
        raise ValueError("無效的問卷識別碼。")
    path = Path(path or DEFAULT_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line and json.loads(line).get("response_id") == response_id:
                return False
    row = dict(version=state.version, response_id=response_id, seed=state.seed, tick=state.tick,
               memorable=memorable, reason=reason.strip(), replay=replay)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    return True
