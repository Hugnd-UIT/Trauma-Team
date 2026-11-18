from .llm import LLM
from . import prompt
from . import state

summary = ""


def trim(text, limit=1200):
    if not text:
        return ""
    s = str(text)
    if len(s) > limit:
        return s[:limit] + "\n...[truncated]"
    return s


def compact(llm=None, max_history=10):
    global summary
    if len(state.history) <= max_history:
        return summary

    bot = llm or LLM()
    keep = state.history[-max_history:]
    old = state.history[:-max_history]

    lines = [f"[{h.get('step')}] {h.get('action')}: {h.get('result')}" for h in old]
    blob = "\n".join(lines)

    text, tin, tout = bot.ask(prompt.SYSTEM, prompt.COMPACT.format(history=blob))
    state.token(tin, tout)

    if text and not text.startswith("[!]"):
        summary = (summary + "\n" + text).strip()

    state.history = keep
    return summary


def prune(seen_clusters):
    cleaned = []
    for h in state.history:
        cid = h.get("detail", {}).get("candidate")
        if cid and cid in seen_clusters and h.get("result") == "reject":
            continue
        cleaned.append(h)
    state.history = cleaned


def build(user_msg, system_msg=None):
    sys = system_msg or prompt.SYSTEM
    msgs = [{"role": "system", "content": sys}]

    if summary:
        msgs.append({"role": "system", "content": f"Context Summary:\n{summary}"})

    # Exclude verbose state history view to optimize prompt tokens
    msgs.append({"role": "user", "content": user_msg})
    return msgs
