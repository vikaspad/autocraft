# src/QATestKitCrew/crew.py
from __future__ import annotations

import os
import sys
import yaml
from pathlib import Path
from typing import Dict, Any, List

# CrewAI core
try:
    from crewai import Agent, Task, Crew, Process
except Exception as e:
    raise RuntimeError("Missing crewai package. Install with `pip install crewai`") from e

# Our tools
try:
    from .tools.custom_tool import TOOLS_REGISTRY, get_tool_by_name
except Exception as e:
    # fallback import path if package name differs locally
    from autocraft.tools.custom_tool import TOOLS_REGISTRY, get_tool_by_name  # type: ignore


ROOT = Path(__file__).resolve().parent
CONFIG_DIR = ROOT / "config"
AGENTS_YAML = CONFIG_DIR / "agents.yaml"
TASKS_YAML  = CONFIG_DIR / "tasks.yaml"


def _load_yaml(path) -> dict:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"YAML file not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a mapping of names -> definitions")
    return data


def _materialize_tools(tool_names: List[str] | None) -> List[Any]:
    tools = []
    for name in (tool_names or []):
        if not name:
            continue
        try:
            tools.append(get_tool_by_name(name))
        except KeyError:
            print(f"[WARN] Tool '{name}' not found in registry; skipping. Known: {list(TOOLS_REGISTRY)}")
    return tools


def _resolve_llm(llm_value: Any) -> Any:
    """
    Agents YAML can provide llm: ${LLM_MODEL} or a literal model name.
    We expand ${ENV_VAR} to its environment value if present.
    """
    if llm_value is None:
        return None
    if isinstance(llm_value, str):
        if llm_value.startswith("${") and llm_value.endswith("}"):
            env_key = llm_value[2:-1]
            return os.getenv(env_key)
        return llm_value
    return llm_value


def _code_exec_defaults() -> dict:
    """
    Global/default code-exec toggles via environment variables.
    - CREW_CODE_EXEC: 1/true enables allow_code_execution for all agents if not explicitly set in YAML
    - CREW_CODE_MODE: 'safe' (Docker) | 'local' (if supported by your CrewAI version)
    - CREW_CODE_TIMEOUT: max seconds per snippet (int)
    - CREW_CODE_RETRIES: retry attempts (int)
    """
    def _truthy(v: str | None) -> bool:
        return str(v).lower() in ("1", "true", "yes", "on")
    d: dict[str, Any] = {}
    if _truthy(os.getenv("CREW_CODE_EXEC")):
        d["allow_code_execution"] = True
    if os.getenv("CREW_CODE_MODE"):
        d["code_execution_mode"] = os.getenv("CREW_CODE_MODE")
    if os.getenv("CREW_CODE_TIMEOUT"):
        try:
            d["max_execution_time"] = int(os.getenv("CREW_CODE_TIMEOUT", "30"))
        except ValueError:
            d["max_execution_time"] = 30
    if os.getenv("CREW_CODE_RETRIES"):
        try:
            d["max_retry_limit"] = int(os.getenv("CREW_CODE_RETRIES", "3"))
        except ValueError:
            d["max_retry_limit"] = 3
    return d


def build_agents(agents_cfg: Dict[str, Any]) -> Dict[str, Agent]:
    """
    Build Agent objects from YAML with safe code-exec defaults:
      - pass through YAML keys:
        allow_code_execution, code_execution_mode, max_execution_time, max_retry_limit
      - optional global defaults from env via _code_exec_defaults()
      - if an agent is named 'coder' and no YAML override is present, enable safe execution
        with Docker ('safe') and (30s, 3 retries) by default
    """
    env_code_defaults = _code_exec_defaults()
    agents: Dict[str, Agent] = {}

    for name, spec in agents_cfg.items():
        if not isinstance(spec, dict):
            print(f"[WARN] Skipping agent '{name}' with invalid spec (expected mapping).")
            continue

        kwargs: Dict[str, Any] = {
            "role":      spec.get("role") or name,
            "goal":      spec.get("goal") or "",
            "backstory": spec.get("backstory") or "",
        }

        # llm can be a literal or ${ENV}
        llm = _resolve_llm(spec.get("llm"))
        if llm:
            kwargs["llm"] = llm

        # tools
        tools = _materialize_tools(spec.get("tools"))
        if tools:
            kwargs["tools"] = tools

        # common flags
        for opt in ("verbose", "cache", "allow_delegation"):
            if opt in spec:
                kwargs[opt] = spec[opt]

        # --- code execution flags (from YAML first) ---
        for opt in ("allow_code_execution", "code_execution_mode", "max_execution_time", "max_retry_limit"):
            if opt in spec:
                kwargs[opt] = spec[opt]

        # --- apply global env defaults if not set in YAML ---
        for k, v in env_code_defaults.items():
            kwargs.setdefault(k, v)

        # --- fallback default for a 'coder' agent if still not set ---
        if name.lower() == "coder":
            kwargs.setdefault("allow_code_execution", True)
            kwargs.setdefault("code_execution_mode", "safe")  # Docker sandbox
            kwargs.setdefault("max_execution_time", 30)
            kwargs.setdefault("max_retry_limit", 3)

        try:
            agents[name] = Agent(**kwargs)
        except TypeError as e:
            print(f"[ERROR] Could not create Agent '{name}': {e}")
            raise
    return agents


def _collect_task_context_text(task_name: str, tasks_cfg: Dict[str, Any]) -> str:
    """Concatenate 'context' tasks' description/expected_output to prime the task input."""
    tcfg = tasks_cfg.get(task_name, {})
    ctx_keys = tcfg.get("context") or []
    chunks: List[str] = []
    for k in ctx_keys:
        ctx = tasks_cfg.get(k, {})
        desc = ctx.get("description") or ""
        exp = ctx.get("expected_output") or ""
        if desc:
            chunks.append(f"[{k}] description:\n{desc.strip()}")
        if exp:
            chunks.append(f"[{k}] expected_output:\n{exp.strip()}")
    return "\n\n".join(chunks).strip()


def build_tasks(tasks_cfg: Dict[str, Any], agents: Dict[str, Agent]) -> Dict[str, Task]:
    tasks: Dict[str, Task] = {}
    for name, spec in tasks_cfg.items():
        if not isinstance(spec, dict):
            print(f"[WARN] Skipping task '{name}' with invalid spec.")
            continue

        agent_key = spec.get("agent")
        if not agent_key or agent_key not in agents:
            raise KeyError(f"Task '{name}' references unknown agent '{agent_key}'. Available: {list(agents)}")

        description = spec.get("description") or ""
        expected_output = spec.get("expected_output")
        output_file = spec.get("output_file")

        # optional input context blob
        ctx_blob = _collect_task_context_text(name, tasks_cfg)
        input_str = f"Context for {name}:\n\n{ctx_blob}" if ctx_blob else None

        kwargs: Dict[str, Any] = {
            "description": description,
            "agent": agents[agent_key],
        }
        if expected_output:
            kwargs["expected_output"] = expected_output
        if output_file:
            kwargs["output_file"] = output_file
        if input_str:
            kwargs["input"] = input_str

        for opt in ("async_execution", "output_json", "human_input"):
            if opt in spec:
                kwargs[opt] = spec[opt]

        try:
            tasks[name] = Task(**kwargs)
        except TypeError as e:
            print(f"[ERROR] Could not create Task '{name}': {e}")
            raise
    return tasks


def build_crew(agents_cfg: Dict[str, Any], tasks_cfg: Dict[str, Any]) -> Crew:
    agents = build_agents(agents_cfg)
    tasks = build_tasks(tasks_cfg, agents)

    # preserve YAML order
    ordered_tasks = [tasks[k] for k in tasks_cfg.keys() if k in tasks]

    crew = Crew(
        agents=list(agents.values()),
        tasks=ordered_tasks,
        process=Process.sequential,
        verbose=True,
    )
    return crew


def run() -> Any:
    agents_cfg = _load_yaml(AGENTS_YAML)
    tasks_cfg = _load_yaml(TASKS_YAML)
    crew = build_crew(agents_cfg, tasks_cfg)

    inputs = {"project": "autocraft"}  # optional high-level input

    print("[Autocraft] Starting Crew run...")
    result = crew.kickoff(inputs=inputs)
    print("\n[Autocraft] Crew finished.")

    return result


if __name__ == "__main__":
    try:
        out = run()
        if isinstance(out, (str, dict)):
            print("\n=== RESULT (truncated) ===")
            s = out if isinstance(out, str) else yaml.safe_dump(out, sort_keys=False)
            print(s[:4000])
    except Exception as e:
        print(f"[FATAL] {e}")
        sys.exit(1)
