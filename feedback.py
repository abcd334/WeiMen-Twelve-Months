"""Fixed-choice, local-only post-game feedback. Never consumes game randomness."""
import json
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parent / "feedback" / "responses.jsonl"


def survey_options(state):
    if not state.ending:
        raise ValueError("遊戲結束後才可填寫問卷。")
    return {
        "memorable": [c.name for c in state.characters] + ["沒有特別記得的人物"],
        "habit": [c.signature for c in state.characters] + ["記不清楚"],
        "hardest": list(dict.fromkeys(f"第 {d['month']} 月：{d['label']}" for d in state.decisions)) + ["沒有特別難決定的選擇"],
        "unfair": ["沒有，重大結果有合理線索", "本局沒有重大人物結果"] + [
            f"第 {m['month']} 月：{state.character(m['character_id']).name}的" +
            {"dead": "死亡", "left": "離開", "defected": "倒戈"}[m["kind"]] for m in state.major_outcomes],
        "replay": ["願意", "也許", "不願意"],
    }


def save_feedback(state, answers, response_id, path=DEFAULT_PATH):
    options = survey_options(state)
    if set(answers) != set(options) or any(answers[key] not in options[key] for key in options):
        raise ValueError("請完成固定選項問卷。")
    if not isinstance(response_id, str) or not response_id or len(response_id) > 100:
        raise ValueError("無效的問卷識別碼。")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                if line.strip() and json.loads(line).get("response_id") == response_id:
                    return False
    record = {"version": state.version, "response_id": response_id, "seed": state.seed,
              "ending": state.ending, "month": state.month, "answers": answers}
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(record, ensure_ascii=False) + "\n")
    return True
