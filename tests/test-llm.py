import os
import sys
import unittest

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from agent import prompt
from agent import state
from agent import context
from agent.llm import LLM


class TestLLM(unittest.TestCase):

    def setUp(self):
        state.init(image="test.img", fs="FAT32")

    def test_prompt_templates_and_schema(self):
        self.assertTrue(len(prompt.SYSTEM) > 0)
        self.assertTrue(len(prompt.USER) > 0)
        self.assertTrue(len(prompt.COMPACT) > 0)
        self.assertIsInstance(prompt.SCHEMA, list)
        self.assertEqual(len(prompt.SCHEMA), 5)

        self.assertNotIn("(", prompt.SYSTEM)
        self.assertNotIn(")", prompt.SYSTEM)
        self.assertNotIn("(", prompt.USER)
        self.assertNotIn(")", prompt.USER)

    def test_state_lifecycle(self):
        self.assertEqual(len(state.history), 0)
        state.record(step=1, action="seam", detail={"cluster": 12}, result="accept")
        self.assertEqual(len(state.history), 1)

        state.update("server.c", "done", chain=[12, 15, 18])
        self.assertIn("server.c", state.done)
        self.assertEqual(state.facts["server.c"], [12, 15, 18])

        state.token(120, 40)
        self.assertEqual(state.tin, 120)
        self.assertEqual(state.tout, 40)

    def test_context_management(self):
        sample_short = "short text"
        self.assertEqual(context.trim(sample_short, limit=50), sample_short)

        sample_long = "B" * 300
        trimmed_result = context.trim(sample_long, limit=50)
        self.assertTrue(trimmed_result.endswith("...[truncated]"))

        state.record(step=2, action="seam", detail={"candidate": 99}, result="reject")
        self.assertEqual(len(state.history), 1)
        context.prune(seen_clusters=[99])
        self.assertEqual(len(state.history), 0)

    def test_llm_initialization(self):
        bot = LLM(model="test-model")
        self.assertEqual(bot.model, "test-model")

        if not bot.client:
            msg, tin, tout = bot.call([{"role": "user", "content": "ping"}])
            self.assertTrue(msg.startswith("[!]"))
            self.assertEqual(tin, 0)
            self.assertEqual(tout, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
