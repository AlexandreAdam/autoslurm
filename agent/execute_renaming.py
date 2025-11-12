from openai import OpenAI
import pathlib

client = OpenAI()


def rename_repo(old="milex_scheduler", new="autoslurm", cli="asl"):
    files = [
        str(p)
        for p in pathlib.Path(".").rglob("*")
        if p.suffix in {".py", ".toml", ".md"} and "agent" not in str(p)
    ]
    tree = "\n".join(files)

    plan = open("agent/memory/rename_plan_autoslurm.md").read()
    response = client.chat.completions.create(
        model="gpt-4.1",
        tools=[
            {
                "type": "python",
                "function": {
                    "name": "edit_file",
                    "description": "Modify text files or move them on disk.",
                },
            }
        ],
        messages=[
            {
                "role": "system",
                "content": (
                    "You can perform filesystem edits directly. "
                    "Use only simple renames and text replacements."
                ),
            },
            {
                "role": "user",
                "content": f"Repository files:\n{tree}\n\nRename plan:\n{plan}",
            },
        ],
    )
    print(response)


if __name__ == "__main__":
    rename_repo()
