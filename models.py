"""Private simulation models and explicit, allow-listed player projections."""
from dataclasses import dataclass, field
from random import Random
import re

GAME_VERSION = "0.5"

SKILLS = {"combat": "武力", "strategy": "智略", "medicine": "醫術", "diplomacy": "交涉"}
RESOURCES = {"treasury": "糧餉", "defense": "山門防備", "reputation": "江湖聲望"}
RISK_NAMES = {"low": "低", "medium": "中", "high": "高", "lethal": "致命風險"}


@dataclass
class Character:
    id: str
    name: str
    age: int
    role: str
    skills: dict
    personality: str
    background: dict
    goal: str
    fear_text: str
    secret: dict
    signature: str
    arc: str
    trust: int = 55
    stress: int = 20
    loyalty: int = 60
    ambition: int = 40
    fear: int = 30
    relationships: dict = field(default_factory=dict)
    fatigue: int = 0
    injury: int = 0
    blocked_until: int = 0
    status: str = "active"
    stage: int = 0
    appearances: int = 0
    choices: list = field(default_factory=list)
    experiences: list = field(default_factory=list)
    history: list = field(default_factory=list)
    recent: str = "尚未有任務或夜談紀錄。"
    recent_month: int = 0
    observed_conditions: set = field(default_factory=set)
    voice: dict = field(default_factory=dict)
    stance: str = ""
    goal_progress: int = 0
    leave_intent: bool = False
    betrayal_intent: bool = False

    def actionable(self, month):
        return self.status == "active" and self.injury < 2 and self.blocked_until < month

    def physical(self, month):
        if self.status != "active":
            return {"dead": "死亡", "left": "離開門派", "defected": "已投靠烈川堂"}[self.status]
        if self.blocked_until >= month:
            return "無法行動（暫停派遣）"
        if self.injury >= 2:
            return "重傷，需留門休養"
        parts = ["輕傷"] if self.injury else []
        if self.fatigue >= 35:
            parts.append("疲勞" if self.fatigue < 65 else "十分疲憊")
        return "、".join(parts) or "健康"

    def public(self, month):
        # Never derive this from asdict(): new private fields must stay private by default.
        recent = self.recent.replace(self.signature, "").strip()
        experiences, seen = [], {re.sub(r"^第\s*\d+\s*月[：:]\s*", "", recent)}
        for experience in reversed(self.experiences):
            text = experience.replace(self.signature, "").strip()
            content = re.sub(r"^第\s*\d+\s*月[：:]\s*", "", text)
            if content and content not in seen:
                seen.add(content)
                experiences.append(text)
        status_label, status_level = self.status_display(month)
        return {"id": self.id, "name": self.name, "age": self.age, "role": SKILLS[self.role],
                "skills": {SKILLS[k]: v for k, v in self.skills.items()},
                "personality": self.personality, "background": self.background["summary"],
                "signature": self.signature, "physical": status_label,
                "actionable": self.actionable(month), "recent": recent,
                "status_label": status_label, "status_level": status_level,
                "actionable_label": "可派遣" if self.actionable(month) else "不可派遣",
                "recent_month": self.recent_month,
                "stance": self.stance,
                "experiences": experiences}

    def status_display(self, month):
        if self.status != "active":
            return {"left": "離開門派", "defected": "倒戈", "dead": "死亡"}[self.status], "unavailable"
        if self.injury >= 2:
            return "重傷休養", "danger"
        if self.blocked_until >= month:
            return "暫停派遣", "unavailable"
        if self.injury:
            return "輕傷", "warning"
        if self.fatigue >= 65:
            return "十分疲憊", "danger"
        if self.fatigue >= 35:
            return "疲憊", "warning"
        if self.fatigue >= 15:
            return "稍有疲勞", "notice"
        return "健康", "normal"


@dataclass
class Cue:
    id: str
    month: int
    character_id: str
    category: str
    strength: str
    text: str
    evidence: dict

    def public(self):
        return {"month": self.month, "character_id": self.character_id, "text": self.text,
                "kind": {"strong": "已證實", "weak": "未解異常", "noise": "人物近況"}[self.strength]}


@dataclass
class GameState:
    seed: int
    rng: Random
    characters: list
    resources: dict = field(default_factory=lambda: {"treasury": 50, "defense": 35, "reputation": 30})
    month: int = 0
    phase: str = "new"
    event_id: str = ""
    seen_events: list = field(default_factory=list)
    flags: set = field(default_factory=set)
    intel: dict = field(default_factory=dict)
    observations: list = field(default_factory=list)
    logs: list = field(default_factory=list)
    facts: list = field(default_factory=list)
    decisions: list = field(default_factory=list)
    pending: list = field(default_factory=list)
    resolved: set = field(default_factory=set)
    last_participants: list = field(default_factory=list)
    night_character: str = ""
    night_scene: dict = field(default_factory=dict)
    used_night_scenes: list = field(default_factory=list)
    version: str = GAME_VERSION
    evidence: dict = field(default_factory=dict)
    leads: list = field(default_factory=list)
    claims: list = field(default_factory=list)
    hypotheses: dict = field(default_factory=dict)
    deduction_history: list = field(default_factory=list)
    investigation_history: list = field(default_factory=list)
    main_thread: str = ""
    story_flags: dict = field(default_factory=dict)
    scene_history: list = field(default_factory=list)
    callback_history: list = field(default_factory=list)
    spotlight_counts: dict = field(default_factory=dict)
    clue_metadata: dict = field(default_factory=dict)
    event_context: dict = field(default_factory=dict)
    pending_callbacks: list = field(default_factory=list)
    thread_beats: list = field(default_factory=list)
    final_priority: str = ""
    last_result: list = field(default_factory=list)
    ending: str = ""
    ending_reason: str = ""
    ending_evidence: list = field(default_factory=list)
    major_outcomes: list = field(default_factory=list)
    option_stats: list = field(default_factory=list)
    counters: dict = field(default_factory=lambda: {"left": 0, "defected": 0, "severe_injury": 0, "dead": 0})

    def character(self, character_id):
        return next(c for c in self.characters if c.id == character_id)

    def active(self):
        return [c for c in self.characters if c.status == "active"]

    def actionable(self):
        return [c for c in self.characters if c.actionable(self.month)]
