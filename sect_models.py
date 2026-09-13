"""v0.7 history models, reusing the existing character and sect state fields."""
from dataclasses import dataclass, field

from models import Character, GameState

GAME_VERSION = "0.7"
STAGES = ("門人", "熟面孔", "核心人物", "門派人物")
FACILITIES = {"training": "練武場", "herbs": "藥圃", "lodge": "客舍"}
JOBS = {"rest": "休養", "train": "修煉", "guard": "守山", "herbs": "照料藥圃", "host": "接待行旅"}
OFFICES = {"medic": "藥堂主事", "leader": "外務領隊", "mentor": "教習"}


def date_label(tick):
    return f"第 {(tick - 1) // 36 + 1} 年 {(tick - 1) % 36 // 3 + 1} 月{('上旬', '中旬', '下旬')[(tick - 1) % 3]}"


@dataclass
class Experience:
    id: str
    tick: int
    kind: str
    text: str
    importance: int
    event_id: str = ""


@dataclass
class SharedMemory:
    id: str
    participants: list[str]
    tick: int
    text: str
    importance: int
    tags: list[str]
    source_ids: list[str]
    # Directed rescue roles must not be inferred from a relationship score.
    actor_id: str = ""
    target_id: str = ""
    recalled_by: list[str] = field(default_factory=list)


@dataclass
class SectCharacter(Character):
    narrative_weight: int = 0
    weight_sources: dict = field(default_factory=dict)
    duties: dict = field(default_factory=dict)
    milestones: set = field(default_factory=set)
    office: str = ""
    last_opportunity: int = 1
    neglect_warnings: list = field(default_factory=list)
    recovery_progress: int = 0
    development: list = field(default_factory=list)


@dataclass
class SectState(GameState):
    version: str = GAME_VERSION
    tick: int = 1
    shared_memories: list[SharedMemory] = field(default_factory=list)
    facilities: dict = field(default_factory=lambda: {key: 1 for key in FACILITIES})
    factions: dict = field(default_factory=lambda: {"商隊": 0, "烈川堂": 0})
    offers: list = field(default_factory=list)
    event_deck: list = field(default_factory=list)
    personal_queue: list = field(default_factory=list)
    triggered: set = field(default_factory=set)
    chain: dict = field(default_factory=lambda: {"step": 0, "due": 4, "clues": 0, "status": "尚未發生"})
    annual_reports: list = field(default_factory=list)
    starvation: int = 0
    last_changes: dict = field(default_factory=dict)

    def actionable(self):
        return [c for c in self.characters if c.actionable(self.tick)]
