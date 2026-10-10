from app.config.model_profiles import ResolvedProfile

HISTORY_OVERHEAD_TOKENS = 256
CONSERVATIVE_CHARS_PER_TOKEN = 2


def budget_optimized_history(
    messages: list[dict[str, str]], profile: ResolvedProfile
) -> list[dict[str, str]]:
    """Trim oldest complete turns using a conservative char budget, not token counts."""
    if profile.name != "optimized" or not messages:
        return list(messages)

    max_tokens = profile.max_tokens or 0
    context_window = profile.context_window or 0
    system_chars = len(profile.system_prompt or "")
    available_input_tokens = max(
        context_window - max_tokens - HISTORY_OVERHEAD_TOKENS,
        0,
    )
    # This is only a safe trimming budget; real token counts come from Ollama metrics.
    char_budget = max(
        available_input_tokens * CONSERVATIVE_CHARS_PER_TOKEN - system_chars,
        0,
    )

    turns: list[list[dict[str, str]]] = []
    for message in messages:
        if message["role"] == "user" or not turns:
            turns.append([message])
        else:
            turns[-1].append(message)

    kept: list[list[dict[str, str]]] = []
    used_chars = 0
    for turn in reversed(turns):
        turn_chars = sum(len(message["content"]) for message in turn)
        if not kept or used_chars + turn_chars <= char_budget:
            kept.append(turn)
            used_chars += turn_chars
        else:
            break
    kept.reverse()
    return [message for turn in kept for message in turn]
