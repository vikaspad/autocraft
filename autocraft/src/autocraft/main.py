#!/usr/bin/env python3
"""
main.py — entrypoint for the Autocraft CrewAI project.

Supports:
- crewai run            -> calls run()
- python -m autocraft.main run|list|validate|print-config
- python -m autocraft.main   (defaults to run)
"""

from __future__ import annotations
import argparse
import os
import sys
from pathlib import Path
import yaml

# Package-safe import (works when installed as 'autocraft') with fallback for script runs
try:
    from . import crew as crew_module
except ImportError:  # script-style fallback
    import crew as crew_module  # type: ignore

ROOT = Path(__file__).resolve().parent
CONFIG_DIR = ROOT / "config"
AGENTS_YAML = CONFIG_DIR / "agents.yaml"
TASKS_YAML  = CONFIG_DIR / "tasks.yaml"


def _load_yaml(path: Path):
    if not path.exists():
        raise FileNotFoundError(f"Missing YAML file: {path}")
    # "r" is for read mode
    # "utf-8" is the encoding of the file
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path} must be a YAML mapping (name -> config)")
    return data


def cmd_list(_: argparse.Namespace) -> int:
    agents = _load_yaml(AGENTS_YAML)
    tasks = _load_yaml(TASKS_YAML)

    print("== Agents ==")
    for name, spec in agents.items():
        llm = spec.get("llm")
        tools = spec.get("tools", [])
        print(f"- {name}: role={spec.get('role')!r}, llm={llm!r}, tools={tools}")

    print("\n== Tasks ==")
    for name, spec in tasks.items():
        agent = spec.get("agent")
        out = spec.get("output_file")
        ctx = spec.get("context")
        print(f"- {name}: agent={agent!r}, output_file={out!r}, context={ctx or []}")
    return 0


def cmd_validate(_: argparse.Namespace) -> int:
    # Let crew module do the heavy lifting (it already validates during build)
    agents = _load_yaml(AGENTS_YAML)
    tasks = _load_yaml(TASKS_YAML)
    # quick checks:
    agent_names = set(agents.keys())
    bad = [(k, v.get("agent")) for k, v in tasks.items() if v.get("agent") not in agent_names]
    if bad:
        lines = "\n".join(f"  - task={t} references missing agent {a!r}" for t, a in bad)
        raise SystemExit(f"Task validation failed; unknown agents:\n{lines}")
    print("Validation OK ✅")
    return 0


def cmd_print_config(_: argparse.Namespace) -> int:
    agents = _load_yaml(AGENTS_YAML)

    print("Paths:")
    print(f"  ROOT:        {ROOT}")
    print(f"  agents.yaml: {AGENTS_YAML}")
    print(f"  tasks.yaml:  {TASKS_YAML}")

    print("\nLLM Resolution:")
    for name, spec in agents.items():
        llm = spec.get("llm")
        if isinstance(llm, str) and llm.startswith("${") and llm.endswith("}"):
            env_key = llm[2:-1]
            resolved = os.getenv(env_key)
        else:
            resolved = llm
        print(f"  - {name}: raw={llm!r}, resolved={resolved!r}")
    return 0


def cmd_run(_: argparse.Namespace) -> int:
    result = crew_module.run()
    if isinstance(result, str):
        print(result)
    else:
        try:
            print(yaml.safe_dump(result, sort_keys=False)[:4000])
        except Exception:
            print(repr(result)[:4000])
    return 0

# Build the parser for the command line arguments
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Autocraft CrewAI runner")
    sub = p.add_subparsers(dest="cmd")

    sub.add_parser("run", help="Run the crew (default)")
    sub.add_parser("list", help="List agents and tasks from YAML")
    sub.add_parser("validate", help="Validate YAML and tool references")
    sub.add_parser("print-config", help="Print effective configuration and model resolution")
    return p

# Main function to run the crew
def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        argv = ["run"]
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.cmd in (None, "run"):
        return cmd_run(args)
    elif args.cmd == "list":
        return cmd_list(args)
    elif args.cmd == "validate":
        return cmd_validate(args)
    elif args.cmd == "print-config":
        return cmd_print_config(args)
    else:
        parser.print_help()
        return 2


# === Entry point for `crewai run` ===
def run():
    """Entry point used by CrewAI CLI (`crewai run`)."""
    return crew_module.run()


if __name__ == "__main__":
    raise SystemExit(main())
