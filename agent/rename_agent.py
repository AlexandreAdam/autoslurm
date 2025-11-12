# agent/rename_agent.py
from datetime import datetime
from openai import OpenAI

client = OpenAI()


def run_rename_agent(old_name="milex_scheduler", new_name="autoslurm", cli="asl"):
    context = open("docs/project_brain.md").read()
    prompt = open("agent/prompts/rename_package.md").read()
    task = (
        f"Refactor the repository from {old_name} to {new_name}, CLI shortname {cli}."
    )

    system = f"{prompt}\n\nProject context:\n{context}"
    response = client.chat.completions.create(
        model="gpt-5-nano",
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": task},
        ],
    )
    result = response.choices[0].message.content

    # Save reasoning and summary
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    with open(f"agent/memory/rename_{new_name}_{ts}.md", "w") as f:
        f.write(f"# Rename Plan\n{result}")
    print(result)


if __name__ == "__main__":
    run_rename_agent()
