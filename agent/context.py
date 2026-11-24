import time
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

    text = None
    for attempt in range(5):
        text, tin, tout = bot.ask(prompt.SYSTEM, prompt.COMPACT.format(history=blob))
        state.token(tin, tout)
        if isinstance(text, list):
            text = str(text)
        if text and not text.startswith("[!]"):
            break
        if attempt < 4:
            time.sleep(4 * (2 ** attempt))

    if text and not text.startswith("[!]"):
        summary = text.strip()[:1000]

    state.history = keep
    return summary


def reset():
    global summary
    summary = ""


def prune(seen_clusters):
    cleaned = []
    for h in state.history:
        cid = h.get("detail", {}).get("candidate")
        if cid and cid in seen_clusters and h.get("result") == "reject":
            continue
        cleaned.append(h)
    state.history = cleaned


def sliding_window(messages, max_turns=6):
    if not messages:
        return []
    sys_msgs = [m for m in messages if m.get("role") == "system"]
    non_sys = [m for m in messages if m.get("role") != "system"]
    keep_count = max_turns * 2
    if len(non_sys) > keep_count:
        non_sys = non_sys[-keep_count:]
    return sys_msgs + non_sys


def build(user_msg, system_msg=None):
    sys = system_msg or prompt.SYSTEM
    msgs = [{"role": "system", "content": sys}]

    if summary:
        msgs.append({"role": "system", "content": f"Context Summary:\n{summary}"})

    # Exclude verbose state history view to optimize prompt tokens
    msgs.append({"role": "user", "content": user_msg})
    return msgs
