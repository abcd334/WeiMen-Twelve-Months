"""Pure authored-text rendering. Accepts only allow-listed public context, never models."""
from hashlib import sha256
import re


def variant(texts, key):
    """Stable choice without consuming game RNG or Python's randomized hash()."""
    return texts[int.from_bytes(sha256(str(key).encode()).digest()[:8], "big") % len(texts)]


def speak(character, message, mood="neutral"):
    voice = character.get("voice", {})
    address = voice.get("address", "掌門")
    lead = voice.get(mood, voice.get("neutral", ""))
    text = lead + message if voice.get("conclusion_first", True) else message + lead
    if voice.get("sentence_length") == "short":
        clauses = [s for s in re.split(r"(?<=[。！？])", text) if s]
        return f"{character['name']}向{address}說：" + "\n".join(f"『{s}』" for s in clauses)
    return f"{character['name']}：『{address}，{text}』"


def render_event_opening(context):
    parts = [context["opening"]]
    if context.get("thread_beat"):
        parts.append(context["thread_beat"])
    parts.extend(c["text"] for c in context.get("callbacks", []))
    if context.get("evidence"):
        parts.append("桌上能核對的只有這些：")
        parts.extend(f"第 {f['month']} 月留下的記錄：{f['text']}" for f in context["evidence"])
        parts.append("這些記錄說明確有異常，卻沒有一項能單獨證明某名弟子通敵。要先查哪裡、是否限制誰的行動，由你決定。")
    return "\n\n".join(parts)


def render_assignment_preview(context, characters):
    lines = []
    for char in characters:
        hook = next((h["text"] for h in context.get("hooks", []) if h["background"] == char["background_id"]), None)
        message = hook or char.get("stance_line", "先把我們答應做的事說清楚，再出發。")
        if context.get("introduction"):
            message = {"武力": "我先試過刀柄了，有兩把得先鎖緊才能拿去守門。", "智略": "欠餉和領糧的兩份單子，我想先放在一起核對。", "醫術": "藥箱我已拿到門邊，誰有傷先說，別到輪值時才撐不住。", "交涉": "山下等著我們答覆的人，我來問清他們各要哪一筆。"}[char["role"]] + char["stance_line"]
        if hook and char.get("voice", {}).get("background_line"):
            message += char["voice"]["background_line"]
        lines.append(speak(char, message, "question" if hook else "neutral"))
    return lines


def render_mission_aftermath(context):
    team = context["participants"]
    if not team:
        return []
    if len(team) == 1:
        message = "說到" + context["detail"] + ("，我先講今日親眼見到的部分。還有疑問的地方，也一起記下。" if context["success"] else "，沒查清的地方，我不想假裝自己知道。")
        return [speak(team[0], message, "supported" if context["success"] else "tense")]
    first, second = team
    if context["bond"] == "strained":
        return [speak(first, "事情辦到哪裡，我會說清楚。但下次改分工前，先告訴我。", "conflict"),
                speak(second, "我當時盯著" + context["detail"] + "。回去把各自看到的說完，再談是誰的錯。", "suspected")]
    return [speak(first, "你剛才替我接住的那一段，我記得。回去說到" + context["detail"] + "，你也把看見的那一段說出來。", "supported"),
            speak(second, "先看大家有沒有跟上。這件事回去一起說。", "other")]


def render_night_scene(context):
    lines = [context["framing"]]
    if context.get("previous"):
        lines.append("上回你選擇了「" + context["previous"] + "」。這次，對方帶著那次安排留下的問題回來。")
    lines.extend(context.get("dialogue", []))
    return "\n\n".join(lines)


def render_relationship_scene(context):
    return render_night_scene(context)


def render_group_scene(context):
    lines = ["議事廳的飯桌推到窗邊，鍋裡還留著熱湯。明日要上斷劍臺，今晚沒有人先收走碗筷。你請仍在門內的人，各說一件明日打算親手完成的事。"]
    for char in context["characters"]:
        memory = char.get("last_choice")
        message = ("你當時選擇「" + memory + "」，我還記得。" if memory else "之前幾次出勤，我都記著。")
        message += char.get("tomorrow", "明日我先核對同伴的位置，再接手自己的工作。")
        lines.append(speak(char, message, char.get("attitude", "neutral")))
    for absent in context["absent"]:
        lines.append(f"{absent['name']}原先坐的位置留著一隻空碗。{absent['memory']}今晚沒有人替那個位置接話。")
    lines.extend("桌邊又提起一件舊事：" + fact["text"] for fact in context.get("callbacks", [])[:2])
    return "\n\n".join(lines)


def render_ending_scene(context):
    # Truth is already gated by the engine; renderer receives no hidden thread data.
    main = context["opening"] + "\n\n這些月的追問，曾從「" + context["motif"] + "」開始。最後能說明多少，仍要回到真正取得的記錄，不能拿留下的人替缺少的證據作保。"
    if context.get("priority"):
        main += "\n\n決戰前夕你選擇「" + context["priority"] + "」。留下的人仍用這句話提醒自己該先照看什麼。"
    callbacks = ["第 " + str(f["month"]) + " 月：" + f["text"] for f in context["callbacks"]]
    return {"final_scene": main, "mystery_reveal": context["mystery"], "callbacks": callbacks}
