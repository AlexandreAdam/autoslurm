#!/usr/bin/env python
"""
LLM-driven agent demo that reads the agent docs and crafts ACP requests.

Set `OPENAI_API_KEY` in your environment to let this script call OpenAI's chat
completion API. When not available it will still run with a very simple
fallback strategy so you can inspect how the docs would be used.
"""

import json
import os
from typing import Dict

from autoslurm.acp import action_definitions, execute_acp


class LLMClient:
    def __init__(self, model: str = "gpt-3.5-turbo"):
        self.model = model
        self.openai, self.client = self._import_openai()

    def _import_openai(self):
        try:
            import openai

            client = None
            if hasattr(openai, "OpenAI"):
                client = openai.OpenAI()
            return openai, client
        except ImportError:
            return None, None

    def compose_schedule_request(
        self, docs: str, actions: Dict[str, dict], script_path: str
    ) -> Dict[str, object]:
        if self.openai and os.environ.get("OPENAI_API_KEY"):
            prompt = self._build_prompt(docs, actions, script_path)
            if self.client:
                print("Using Client")
                completion = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {
                            "role": "system",
                            "content": "You are an AutoSlurm agent that speaks ACP.",
                        },
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.2,
                )
                content = completion.choices[0].message.content.strip()
            else:
                print("using openai old API")
                completion = self.openai.ChatCompletion.create(
                    model=self.model,
                    messages=[
                        {
                            "role": "system",
                            "content": "You are an AutoSlurm agent that speaks ACP.",
                        },
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.2,
                )
                content = completion.choices[0].message.content.strip()
            return json.loads(content)
        else:
            raise ValueError
            # # Fallback for offline testing.
            # bundle = "llm_agent_bundle"
            # job = {
                # "name": "llm_job",
                # "script": "python tests/scripts/hello_script.py",
                # "slurm": {"time": "00:02:00", "cpus_per_task": 1, "mem": "1G"},
            # }
            # return {"action": "schedule", "bundle": bundle, "job": job, "append": False}

    def _build_prompt(
        self, docs: str, actions: Dict[str, dict], script_path: str
    ) -> str:
        action_list = "\n".join(
            f"- {name}: {meta['description']}" for name, meta in actions.items()
        )
        return (
            "Documentation:\n"
            f"{docs}\n"
            "You have read the compiled AutoSlurm agent reference."
            "Compose an ACP JSON payload that schedules a small script. "
            f"Available actions:\n{action_list}\n"
            f"The script path you must run is EXACT: {script_path}\n"
            "Respond with raw JSON only."
        )


def run_agent():
    """
    Observation 1: including the full agent documentation is too much context. The agent does not do a proper job.
    Not included is perhaps not enough context. The agent outputs the correct schema (ACP), 
    but there is some variability in the output which ultimately renders invalid the action.
    The next agent demo will include a more refined workflow where we included engineered context 
    for each task.
    
    Observation 2: Documentation should be at the beginning, and then a sentence to say that was the docs.
    This solve the issue with the agent not producing a json.
    Finally, context engineering has solved some of the variance in the output. For this simple task, theere should essentially be none.
    """
    docs = fetch_schedule_context()
    print(f"[Agent] Loaded {len(docs)} characters of scheduling documentation.")
    actions = action_definitions()
    print("[Agent] Available ACP actions:", ", ".join(actions.keys()))

    llm = LLMClient()
    script_path = "python tests/scripts/hello_script.py"
    request = llm.compose_schedule_request(docs, actions, script_path)
    print("[Agent] Generated request:\n", json.dumps(request, indent=4))
    response = execute_acp(request)
    print("[Agent] Response:\n", json.dumps(response, indent=4))


def fetch_schedule_context() -> str:
    response = execute_acp({"action": "gather_context", "task": "schedule"})
    if response["status"] != "success":
        raise SystemExit("Unable to gather schedule context")
    return response["result"]


if __name__ == "__main__":
    run_agent()
