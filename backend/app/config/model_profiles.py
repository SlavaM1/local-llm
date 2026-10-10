from dataclasses import asdict, dataclass
from typing import Literal


ProfileName = Literal["baseline", "optimized"]

OPTIMIZED_SYSTEM_PROMPT = """Ты краткий и практичный помощник разработчика по Java, Spring, SQL, Docker, backend, REST, Linux, LLM, RAG и архитектуре. Отвечай на языке пользователя. Сначала давай решение, не повторяй вопрос и избегай длинных вступлений. Оформляй код в Markdown-блоках, пиши современный читаемый код. Если информации недостаточно, прямо скажи об этом; не выдумывай API. Кратко объясняй существенные компромиссы и оставайся лаконичным."""


@dataclass(frozen=True)
class ModelProfile:
    name: ProfileName
    model: str
    system_prompt: str | None
    temperature: float | None
    max_tokens: int | None
    context_window: int | None
    top_p: float | None
    repeat_penalty: float | None
    thinking: bool

    def metadata(self) -> dict:
        data = asdict(self)
        data["id"] = data.pop("name")
        data["label"] = "Baseline" if self.name == "baseline" else "Optimized"
        data["system_prompt"] = data["system_prompt"] or ""
        data["customizable"] = self.name == "optimized"
        return data


@dataclass(frozen=True)
class ResolvedProfile:
    name: ProfileName
    model: str
    system_prompt: str | None
    temperature: float | None
    max_tokens: int | None
    context_window: int | None
    top_p: float | None
    repeat_penalty: float | None
    thinking: bool

    def settings_dict(self) -> dict:
        if self.name == "baseline":
            return {"thinking": self.thinking}
        return {
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "context_window": self.context_window,
            "top_p": self.top_p,
            "repeat_penalty": self.repeat_penalty,
            "thinking": self.thinking,
        }


MODEL_PROFILES: dict[ProfileName, ModelProfile] = {
    "baseline": ModelProfile(
        name="baseline",
        model="qwen3:8b",
        system_prompt=None,
        temperature=None,
        max_tokens=None,
        context_window=None,
        top_p=None,
        repeat_penalty=None,
        thinking=False,
    ),
    "optimized": ModelProfile(
        name="optimized",
        model="qwen3-dev:8b",
        system_prompt=OPTIMIZED_SYSTEM_PROMPT,
        temperature=0.2,
        max_tokens=512,
        context_window=4096,
        top_p=0.9,
        repeat_penalty=1.08,
        thinking=False,
    ),
}


def resolve_profile(
    name: ProfileName,
    *,
    temperature: float | None = None,
    max_tokens: int | None = None,
    context_window: int | None = None,
    thinking: bool | None = None,
) -> ResolvedProfile:
    profile = MODEL_PROFILES[name]
    if name == "baseline":
        return ResolvedProfile(**asdict(profile))
    return ResolvedProfile(
        name=profile.name,
        model=profile.model,
        system_prompt=profile.system_prompt,
        temperature=profile.temperature if temperature is None else temperature,
        max_tokens=profile.max_tokens if max_tokens is None else max_tokens,
        context_window=profile.context_window if context_window is None else context_window,
        top_p=profile.top_p,
        repeat_penalty=profile.repeat_penalty,
        thinking=profile.thinking if thinking is None else thinking,
    )


def profile_metadata() -> dict:
    return {
        "profiles": [profile.metadata() for profile in MODEL_PROFILES.values()],
        "allowed": {
            "temperatures": [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
            "max_tokens": [256, 512, 1024],
            "context_windows": [2048, 4096],
            "thinking": [False, True],
        },
    }
