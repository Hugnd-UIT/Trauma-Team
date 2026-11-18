import os
import time
import random
from openai import OpenAI


class LLM:
    def __init__(self, model=None, temp=0.2, top=1.0, tokens=1024):
        self.model = model or os.getenv("MODEL") or os.getenv("OPENAI_MODEL", "openai/gpt-4o-mini")
        self.temp = temp
        self.top = top
        self.tokens = tokens
        self.client = self.init()

    def init(self):
        key = os.getenv("KEY") or os.getenv("OPENAI_API_KEY")
        if not key:
            return None
        url = os.getenv("URL") or os.getenv("OPENAI_BASE_URL")
        if url:
            return OpenAI(api_key=key, base_url=url)
        return OpenAI(api_key=key)

    def call(self, messages, tools=None):
        if not self.client:
            return "[!] OpenAI API key not configured.", 0, 0
        last = None
        for i in range(5):
            try:
                kwargs = {
                    "model": self.model,
                    "messages": messages,
                    "temperature": self.temp,
                    "top_p": self.top,
                    "max_tokens": self.tokens,
                    "timeout": 60,
                }
                if tools:
                    kwargs["tools"] = tools

                res = self.client.chat.completions.create(**kwargs)
                if not getattr(res, "choices", None):
                    last = "Empty choices"
                    time.sleep(1 + random.random())
                    continue

                choice = res.choices[0].message
                tin = getattr(res.usage, "prompt_tokens", 0) if hasattr(res, "usage") else 0
                tout = getattr(res.usage, "completion_tokens", 0) if hasattr(res, "usage") else 0

                # Native OpenAI tool calls support
                if getattr(choice, "tool_calls", None):
                    return choice.tool_calls, tin, tout

                return choice.content or "", tin, tout

            except Exception as e:
                last = e
                wait = min(2 ** i, 15) + random.random()
                time.sleep(wait)

        return f"[!] LLM error: {last}", 0, 0

    def ask(self, system, user):
        msg = [
            {"role": "system", "content": system},
            {"role": "user", "content": user}
        ]
        return self.call(msg)
