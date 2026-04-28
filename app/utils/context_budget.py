"""Context budget management for small local LLMs (Gemma 2B/4B).

Estimates token counts and truncates prompts to fit within context windows.
Uses a simple word-based heuristic: ~1.3 tokens per word for English text.
"""

TOKENS_PER_WORD = 1.3
DEFAULT_CTX_BUDGET = 4096
RESPONSE_RESERVE = 1024


def estimate_tokens(text):
    """Estimate token count from text using word-based heuristic."""
    if not text:
        return 0
    return int(len(text.split()) * TOKENS_PER_WORD)


def truncate_to_tokens(text, max_tokens):
    """Truncate text to fit within a token budget. Cuts at word boundaries."""
    if not text:
        return text
    max_words = int(max_tokens / TOKENS_PER_WORD)
    words = text.split()
    if len(words) <= max_words:
        return text
    return ' '.join(words[:max_words]) + '\n[...truncated for context length...]'


def budget_prompt(prompt, system=None, ctx_size=DEFAULT_CTX_BUDGET):
    """Ensure prompt + system fit within context budget, truncating prompt if needed.

    Reserves RESPONSE_RESERVE tokens for the model's output.
    Returns (prompt, system) — possibly truncated.
    """
    available = ctx_size - RESPONSE_RESERVE
    system_tokens = estimate_tokens(system) if system else 0
    prompt_tokens = estimate_tokens(prompt)

    if system_tokens + prompt_tokens <= available:
        return prompt, system

    prompt_budget = available - system_tokens
    if prompt_budget < 200:
        system = truncate_to_tokens(system, available // 2)
        prompt_budget = available - estimate_tokens(system)

    return truncate_to_tokens(prompt, prompt_budget), system
