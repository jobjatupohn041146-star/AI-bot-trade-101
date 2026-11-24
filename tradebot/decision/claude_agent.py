"""Claude as the final decision maker. It sees the full multi-school market
context, the candidate from the rule engine, the psychological state, the
account and its own trade statistics, and must reason through all 3 pillars.
Hard psychology and money-management rules are still enforced afterwards."""
from __future__ import annotations

import json

import anthropic

from ..curriculum import knowledge_text

SYSTEM = """You are an autonomous trading agent. You trade only what your playbook
allows. For every request you must reason through three pillars in order:
1. Psychology - is this a disciplined trade or FOMO / revenge / overtrading?
2. Technical analysis - confluence across Price Action, SMC, ICT and Elliott Wave.
3. Money management - is the structural invalidation sensible for sizing?
HOLD is always acceptable and is the default when evidence is mixed.
Use your journal statistics: favour setups with positive expectancy, be
sceptical of setups with negative expectancy. Never set a fixed take profit;
exits are managed by the statistics-driven exit policy."""

DECISION_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["BUY", "SELL", "HOLD"]},
        "setup": {"type": "string"},
        "confidence": {"type": "number"},
        "psychology_check": {"type": "string"},
        "technical_analysis": {"type": "string"},
        "money_management_check": {"type": "string"},
        "invalidation_price": {"type": ["number", "null"]},
        "reasoning": {"type": "string"},
    },
    "required": ["action", "setup", "confidence", "psychology_check", "technical_analysis",
                 "money_management_check", "invalidation_price", "reasoning"],
    "additionalProperties": False,
}


def _jsonable(ctx: dict) -> dict:
    return {k: v for k, v in ctx.items() if k != "swings"}


class ClaudeTrader:
    def __init__(self, playbook: str, model: str = "claude-opus-5-5", effort: str = "medium",
                 client: anthropic.Anthropic | None = None):
        self.client = client or anthropic.Anthropic()
        self.model = model
        self.effort = effort
        # Stable prefix (instructions + playbook + curriculum) is cached across calls.
        self.system = [
            {"type": "text", "text": SYSTEM},
            {"type": "text", "text": f"<playbook>\n{playbook}\n</playbook>\n\n<curriculum>\n{knowledge_text()}\n</curriculum>",
             "cache_control": {"type": "ephemeral"}},
        ]

    def decide(self, ctx: dict, candidate: dict, psychology: dict, account: dict,
               stats: dict, exit_plan: dict) -> dict:
        payload = {
            "market_context": _jsonable(ctx),
            "rule_engine_candidate": candidate,
            "psychology_state": psychology,
            "account": account,
            "journal_stats_by_setup": stats,
            "exit_plan_for_candidate_setup": exit_plan,
        }
        try:
            msg = self.client.beta.messages.create(
                model=self.model,
                max_tokens=16000,
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
                output_config={"effort": self.effort,
                               "format": {"type": "json_schema", "schema": DECISION_SCHEMA}},
                system=self.system,
                messages=[{"role": "user", "content": "Decide on this bar.\n" + json.dumps(payload, default=str)}],
            )
        except (anthropic.RateLimitError, anthropic.APIConnectionError, anthropic.APIStatusError) as e:
            return self._hold(f"API error: {type(e).__name__}")
        if msg.stop_reason == "refusal":
            return self._hold("model declined")
        if msg.stop_reason == "max_tokens":
            return self._hold("truncated response")
        text = next((b.text for b in msg.content if b.type == "text"), "")
        try:
            d = json.loads(text)
        except json.JSONDecodeError:
            return self._hold("unparseable response")
        d["confidence"] = max(0.0, min(1.0, float(d.get("confidence", 0))))
        return d

    @staticmethod
    def _hold(reason: str) -> dict:
        return {"action": "HOLD", "setup": "", "confidence": 0.0, "psychology_check": "",
                "technical_analysis": "", "money_management_check": "",
                "invalidation_price": None, "reasoning": reason}
