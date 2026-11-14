"""Read-only interface coverage check; never imports AutoSlurm or its clients.

Run with .development/python REFACTORING_DOCS/design/check_mvp10_inventory.py.
--discover prints source identities for review; it does not approve new entries.
This checks inventory coverage, not diagnostic implementation or behavior.
"""

import ast
import importlib.util
import json
from pathlib import Path
import sys
import tomllib


ROOT = Path(__file__).resolve().parents[2]
REGISTER = Path(__file__).with_name("MVP10_api_inventory.json")
EXPLICIT_COMPATIBILITY = {
    "autoslurm.context.agent_context": "autoslurm.context.agent_context",
    "autoslurm.context.agent_context_paths": "autoslurm.context.agent_context_paths",
    "autoslurm.sync.sync_machine": "autoslurm.sync.sync_machine",
    **{f"autoslurm.logs.{name}": f"autoslurm.experiment_context.{name}"
       for name in ("experiment_context", "job_context", "latest_log_context")},
}


def discover(root=ROOT):
    package = root / "src" / "autoslurm"
    trees = {}
    imports = {}
    for path in sorted(package.rglob("*.py")):
        relative = path.relative_to(root / "src").with_suffix("")
        module = ".".join(relative.parts)
        if module.endswith(".__init__"):
            module = module.removesuffix(".__init__")
        tree = ast.parse(path.read_text(), filename=str(path))
        trees[module] = tree
        bindings = {}
        parent = module if path.name == "__init__.py" else module.rpartition(".")[0]
        for node in tree.body:
            if isinstance(node, ast.ImportFrom):
                target = importlib.util.resolve_name("." * node.level + (node.module or ""), parent) if node.level else node.module
                for alias in node.names:
                    bindings[alias.asname or alias.name] = target + "." + alias.name
        imports[module] = bindings

    def resolve(symbol):
        seen = set()
        while symbol not in seen:
            seen.add(symbol)
            module, _, name = symbol.rpartition(".")
            replacement = imports.get(module, {}).get(name)
            if replacement is None:
                return symbol
            symbol = replacement
        raise ValueError(f"Cyclic re-export: {symbol}")

    def assignment(tree, name):
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
                return node.value
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == name:
                return node.value
        return None

    interfaces = {"python:" + name: resolve(owner) for name, owner in EXPLICIT_COMPATIBILITY.items()}
    for module, tree in trees.items():
        exported = assignment(tree, "__all__")
        if exported is not None:
            for name in ast.literal_eval(exported):
                interfaces["python:" + module + "." + name] = resolve(module + "." + name)
    for owner in sorted(set(interfaces.values())):
        module, _, name = owner.rpartition(".")
        definition = next((node for node in trees[module].body if isinstance(node, ast.ClassDef) and node.name == name), None)
        if definition:
            for method in definition.body:
                if isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)) and not method.name.startswith("_"):
                    interfaces["method:" + owner + "." + method.name] = owner + "." + method.name

    root_tree = trees["autoslurm.apps.root"]
    handlers = assignment(root_tree, "ACTION_HANDLERS")
    actions = {}
    for key, value in zip(handlers.keys, handlers.values):
        binding, _, member = ast.unparse(value).partition(".")
        actions[ast.literal_eval(key)] = imports["autoslurm.apps.root"][binding] + "." + member
    for action, owner in actions.items():
        interfaces["cli:" + action] = resolve(owner)
    for alias, action in ast.literal_eval(assignment(root_tree, "ACTION_ALIASES")).items():
        interfaces["cli-alias:" + alias] = interfaces["cli:" + action]
    for action, owner in actions.items():
        for node in ast.walk(trees[owner.rpartition(".")[0]]):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "add_parser" and node.args
                    and isinstance(node.args[0], ast.Constant)):
                interfaces["cli-subaction:" + action + " " + node.args[0].value] = resolve(owner)
    scripts = tomllib.loads((root / "pyproject.toml").read_text())["project"]["scripts"]
    for name, target in scripts.items():
        interfaces["console:" + name] = resolve(target.replace(":", "."))
    for module, tree in trees.items():
        for node in tree.body:
            if isinstance(node, ast.If) and "__name__" in ast.unparse(node.test) and "__main__" in ast.unparse(node.test):
                interfaces["module:" + module] = resolve(module + ".main")
    metadata = json.loads((package / "acp_action.json").read_text())
    actions = {entry["name"] for entry in metadata}
    dispatch = {node.comparators[0].value for node in ast.walk(trees["autoslurm.acp"])
                if isinstance(node, ast.Compare) and isinstance(node.left, ast.Name) and node.left.id == "action"
                and len(node.comparators) == 1 and isinstance(node.comparators[0], ast.Constant)}
    if dispatch != actions:
        raise ValueError(f"ACP metadata/dispatch mismatch: {dispatch ^ actions}")
    for action in actions:
        interfaces["acp:" + action] = "autoslurm.acp.execute_acp"

    broad_catches = {}
    for module, tree in trees.items():
        def walk(node, scope):
            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    walk(child, scope + "." + child.name)
                else:
                    if isinstance(child, ast.ExceptHandler):
                        caught = ast.unparse(child.type) if child.type else "bare"
                        if child.type is None or any(isinstance(n, ast.Name) and n.id in {"Exception", "BaseException"} for n in ast.walk(child.type)):
                            broad_catches.setdefault(scope, []).append(caught)
                    walk(child, scope)
        walk(tree, module)
    return {"interfaces": dict(sorted(interfaces.items())), "broad_catches": dict(sorted(broad_catches.items()))}


def check(register, discovered):
    errors = []
    for section in ("interfaces", "broad_catches"):
        actual, expected = discovered[section], register[section]
        for key in sorted(actual.keys() | expected.keys()):
            if actual.get(key) != expected.get(key):
                errors.append(f"{section}: {key}: registered={expected.get(key)!r}; source={actual.get(key)!r}")
    owners = set(discovered["interfaces"].values())
    if owners != register["owners"].keys():
        errors.append(f"Owner coverage mismatch: {owners ^ register['owners'].keys()}")
    for owner, row in register["owners"].items():
        for field in ("contract", "inputs", "current", "effects"):
            if not row.get(field):
                errors.append(f"{owner}: missing {field}")
        if row.get("contract") not in register["contracts"]:
            errors.append(f"{owner}: unknown contract")
    for key, contract in register["contracts"].items():
        for field in ("failures", "translation_owner", "desired_diagnostic", "next_action", "regression_evidence", "implementation_task"):
            if not contract.get(field):
                errors.append(f"{key}: missing {field}")
        for path in contract.get("regression_evidence", []):
            if not (ROOT / path).is_file():
                errors.append(f"{key}: missing regression source {path}")
    if register["broad_catches"].keys() != register["catch_reviews"].keys():
        errors.append("Broad-catch review coverage mismatch")
    for owner, catches in discovered["broad_catches"].items():
        reviews = register["catch_reviews"].get(owner, [])
        if len(catches) != len(reviews) or any(not review for review in reviews):
            errors.append(f"{owner}: each broad catch needs its own review")
    for route, notes in register.get("route_notes", {}).items():
        if route not in discovered["interfaces"]:
            errors.append(f"Unknown route note: {route}")
        if "contract" in notes and notes["contract"] not in register["contracts"]:
            errors.append(f"{route}: unknown contract")
    for route in discovered["interfaces"]:
        if route.startswith(("acp:", "cli-subaction:")):
            notes = register.get("route_notes", {}).get(route, {})
            for field in ("inputs", "current", "effects", "contract"):
                if not notes.get(field):
                    errors.append(f"{route}: missing action-specific {field}")
    return errors


if __name__ == "__main__":
    discovered = discover()
    if sys.argv[1:] == ["--discover"]:
        print(json.dumps(discovered, indent=2))
    elif sys.argv[1:]:
        raise SystemExit("Use no arguments to check, or --discover to print source identities.")
    else:
        register = json.loads(REGISTER.read_text())
        errors = check(register, discovered)
        if errors:
            raise SystemExit("\n".join(errors))
        print(f"Coverage matches: {len(discovered['interfaces'])} routes, {len(register['owners'])} owners, "
              f"{sum(map(len, discovered['broad_catches'].values()))} broad catches. Diagnostic adoption remains pending.")
