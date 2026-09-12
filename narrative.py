"""Pure authored-text rendering. Accepts only allow-listed public context, never models."""
from hashlib import sha256


def variant(texts, key):
    """Stable choice without consuming game RNG or Python's randomized hash()."""
    return texts[int.from_bytes(sha256(str(key).encode()).digest()[:8], "big") % len(texts)]


def speak(character, message, mood="neutral"):
    # Message is already authored as complete sentences. Personality may select a
    # variant elsewhere, but must never prepend/append unrelated stance fragments.
    return f"{character['name']}：『{message}』"


def render_character_opinion(context, character):
    if not character["actionable"]:
        if character["physical"] in ("死亡", "離開門派", "倒戈"):
            return {"thought":"本月未在門內參與議事。", "dialogue":""}
        return {"thought":"目前不能出勤，可以留門核對已知記錄。", "dialogue":"這次我不能出門，能看過的資料請留一份給我。"}
    variants = context.get("character_views", {}).get(character["role_id"], [])
    if not variants:
        return {"thought":"先看清本月要處理的事。", "dialogue":"請先把已知的經過說完，我再判斷能幫哪一段。"}
    return dict(variant(variants, (context["key"], character["id"], character["personality"])))


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
    return [speak(char, render_character_opinion(context, char)["dialogue"]) for char in characters]


def render_mission_aftermath(context):
    team = context["participants"]
    if not team:
        return []
    if len(team) == 1:
        # The authored result and investigation already explain this person's work.
        return []
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
