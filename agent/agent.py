"""
A minimal local orchestrator for LLM-assisted development.
Reads context, takes a user task, and calls the model to propose code changes.
"""

from datetime import date
from openai import OpenAI


def load_context():
    files = [
        "docs/project_map.md",
        # "docs/agent_context.md",
        # "docs/experiments_catalog.md"
    ]
    context = ""
    for f in files:
        with open(f) as fp:
            context += "\n\n" + fp.read()
    return context


def ask_agent(task: str):
    client = OpenAI()
    system = load_context()
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": task},
    ]
    response = client.chat.completions.create(model="gpt-4.1", messages=messages)
    content = response.choices[0].message.content
    # Save plan to memory
    with open(f"agent/memory/{date.today()}_plan.md", "w") as f:
        f.write(f"# Task\n{task}\n\n# Response\n{content}")
    return content


if __name__ == "__main__":
    task = input("Task for the agent: ")
    print(ask_agent(task))
