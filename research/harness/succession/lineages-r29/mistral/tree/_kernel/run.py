"""Kernel implementation of sandboxed gate execution, ledgering, and cost tracking.

This module implements the exact API surface required by the kernel seam in run_check.py,
including sandboxing, environment scrubbing, gate execution, cost ledgering, and timeout handling.
"""

import json
import os
import shutil
import subprocess
import tempfile
import time
import uuid
import hashlib
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union


# Seam values
_REQ_OPS = ('<=', '>=', '==', '!=', '~=', '<', '>')
_BWRAP_OK = None


# Constants
SANDBOX_BACKENDS = {"none", "seatbelt", "bubblewrap", "inherited"}
GATE_TIMEOUT_DEFAULT = 60.0  # Default gate timeout in seconds
GATE_TIMEOUT_ENV = "RETICULI_GATE_TIMEOUT"
LEDGER_FILE = "ledger.json"
STORE_DIR = ".reticuli"


# Environment scrubbing
def _scrub_env() -> Dict[str, str]:
    """Return a scrubbed environment for gate execution."""
    env = {
        "PATH": os.getenv("PATH", ""),
        "HOME": os.getenv("HOME", ""),
        "TMPDIR": os.getenv("TMPDIR", ""),
        "LANG": os.getenv("LANG", "C"),
        "LC_ALL": os.getenv("LC_ALL", "C"),
    }
    # Allow RETICULI_* variables to pass through
    for k, v in os.environ.items():
        if k.startswith("RETICULI_"):
            env[k] = v
    return env


def _env_cache_dir() -> str:
    """Return the path to the cache directory for furnished environments."""
    cache_dir = os.path.join(os.path.expanduser("~"), ".cache", "reticuli", "env")
    os.makedirs(cache_dir, exist_ok=True)
    return cache_dir


def _have(tool: str) -> bool:
    """Check if a tool is available in the PATH."""
    return shutil.which(tool) is not None


def _bwrap_usable() -> bool:
    """Check if bubblewrap is available and usable."""
    return _have("bwrap") and subprocess.run(
        ["bwrap", "--dev", "/dev/null", "true"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).returncode == 0


def _tool_version(tool: str) -> Optional[Tuple[int, ...]]:
    """Get the version of a tool as a tuple of integers."""
    try:
        result = subprocess.run(
            [tool, "--version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        version_str = result.stdout.strip() or result.stderr.strip()
        # Extract version numbers (e.g., "bwrap 0.4.1" -> (0, 4, 1))
        for part in version_str.split():
            if part[0].isdigit():
                return tuple(int(x) for x in part.split(".") if x.isdigit())
        return None
    except Exception:
        return None


def _version_ok(tool: str, min_version: Tuple[int, ...]) -> bool:
    """Check if a tool's version meets the minimum requirement."""
    version = _tool_version(tool)
    if version is None:
        return False
    return version >= min_version


def _version_tuple(version_str: str) -> Tuple[int, ...]:
    """Convert a version string to a tuple of integers."""
    return tuple(int(x) for x in version_str.split(".") if x.isdigit())


def sandbox_backend() -> str:
    """Determine the available sandbox backend."""
    if os.getenv("RETICULI_JAILED") == "1":
        return "inherited"
    if _bwrap_usable():
        return "bubblewrap"
    return "none"


def _in_band(req: str) -> bool:
    """Check if a requirement is in the allowed band."""
    if req.startswith("python:"):
        module = req[7:]
        try:
            __import__(module)
            return True
        except ImportError:
            return False
    return _have(req)


def independence(producer: Dict[str, Any], record: Optional[Dict[str, Any]] = None) -> str:
    """Return a string describing producer independence."""
    return _independence_line(producer)


def _independence_line(producer: Dict[str, Any]) -> str:
    """Generate a line for producer independence."""
    vendor = producer.get("vendor", "unknown")
    model = producer.get("model", "unknown")
    return f"independence: {vendor}/{model}"


def _kill_tree(pid: int) -> bool:
    """Kill a process tree."""
    try:
        subprocess.run(["pkill", "-TERM", "-P", str(pid)], check=False)
        subprocess.run(["kill", "-TERM", str(pid)], check=False)
        return True
    except Exception:
        return False


def _ledger_path(d: str) -> str:
    """Return the path to the ledger file."""
    return os.path.join(d, STORE_DIR, LEDGER_FILE)


def _quote_sb(s: str) -> str:
    """Quote a string for seatbelt sandbox."""
    return f"'{s}'"


def _run(argv: List[str], cwd: str, env: Dict[str, str], timeout: float) -> Dict[str, Any]:
    """Run a command with a timeout and return its status."""
    try:
        result = subprocess.run(
            argv,
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
        return {
            "status": "ok" if result.returncode == 0 else "failed",
            "returncode": result.returncode,
            "stdout": result.stdout.decode("utf-8", errors="replace"),
            "stderr": result.stderr.decode("utf-8", errors="replace"),
        }
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "returncode": None, "stdout": "", "stderr": ""}
    except Exception as e:
        return {"status": "failed", "returncode": None, "stdout": "", "stderr": str(e)}


def _sandbox_argv(backend: str, argv: List[str], cwd: str) -> List[str]:
    """Generate sandboxed command arguments."""
    if backend == "bubblewrap":
        return [
            "bwrap",
            "--die-with-parent",
            "--unshare-all",
            "--new-session",
            "--dir", "/tmp",
            "--dir", "/dev",
            "--dev", "/dev/null",
            "--proc", "/proc",
            "--tmpfs", "/home",
            "--ro-bind", "/etc/resolv.conf", "/etc/resolv.conf",
            "--ro-bind", cwd, cwd,
            "--chdir", cwd,
            "--setenv", "HOME", "/home/user",
            "--setenv", "TMPDIR", "/tmp",
            "--setenv", "PATH", os.getenv("PATH", ""),
            "--"
        ] + argv
    else:
        return argv


def _run_gate_internal(
    run_cmd: str,
    d: str,
    recipe: Optional[Dict[str, Any]] = None,
    timeout: Optional[float] = None,
) -> Dict[str, Any]:
    """Internal implementation of run_gate."""
    backend = sandbox_backend()
    env = _scrub_env()
    
    # Create a scratch directory for the gate
    scratch_dir = os.path.join(d, STORE_DIR, "scratch", str(uuid.uuid4()))
    os.makedirs(scratch_dir, exist_ok=True)
    env["TMPDIR"] = scratch_dir
    env["HOME"] = scratch_dir
    
    # Determine timeout
    if timeout is None:
        timeout = gate_timeout(recipe)
    
    # Prepare the command
    argv = ["sh", "-c", run_cmd]
    sandboxed_argv = _sandbox_argv(backend, argv, d)
    
    # Run the command
    start_time = time.time()
    result = _run(sandboxed_argv, d, env, timeout)
    elapsed = time.time() - start_time
    
    # Clean up scratch directory
    shutil.rmtree(scratch_dir, ignore_errors=True)
    
    # Record the result
    return {
        "status": result["status"],
        "quarantine": backend,
        "returncode": result["returncode"],
        "stdout": result["stdout"],
        "stderr": result["stderr"],
        "elapsed": elapsed,
    }


def gate_timeout(recipe: Optional[Dict[str, Any]] = None) -> float:
    """Determine the effective gate timeout.

    The declared gate_timeout in the recipe is the ceiling, not the default.
    """
    host_ceiling = float(os.getenv(GATE_TIMEOUT_ENV, float('inf')))
    
    if recipe is not None and "claim" in recipe:
        declared = recipe["claim"].get("gate_timeout")
        if declared is not None:
            return min(declared, host_ceiling)
    
    return min(float(os.getenv(GATE_TIMEOUT_ENV, GATE_TIMEOUT_DEFAULT)), host_ceiling)


def run_gate(
    run_cmd: str,
    d: str,
    recipe: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Run a gate command in a sandboxed environment."""
    return _run_gate_internal(run_cmd, d, recipe)


def sandbox() -> Dict[str, Any]:
    """Probe the sandbox backend and its capabilities."""
    backend = sandbox_backend()
    if backend == "bubblewrap":
        return {"backend": backend, "version": _tool_version("bwrap")}
    else:
        return {"backend": backend}


def preflight(recipe: Dict[str, Any]) -> List[str]:
    """Check the environment contract for missing requirements."""
    missing = []
    for req in recipe.get("claim", {}).get("requires", []):
        if not _in_band(req):
            missing.append(req)
    return missing


def ledger(d: str, event: Dict[str, Any]) -> None:
    """Append an event to the ledger."""
    ledger_path = Path(_ledger_path(d))
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    
    events = []
    if ledger_path.exists():
        with open(ledger_path, "r", encoding="utf-8") as f:
            try:
                events = json.load(f)
            except json.JSONDecodeError:
                events = []
    
    events.append(event)
    
    with open(ledger_path, "w", encoding="utf-8") as f:
        json.dump(events, f, indent=2)


def ledger_events(d: str) -> List[Dict[str, Any]]:
    """Return all events in the ledger."""
    ledger_path = Path(_ledger_path(d))
    if not ledger_path.exists():
        return []
    
    with open(ledger_path, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return []


def cost(d: str) -> Optional[Dict[str, Union[float, int]]]:
    """Return the total cost from the ledger."""
    events = ledger_events(d)
    totals = {}
    
    for event in events:
        for k, v in event.items():
            if k in ("usd", "tokens", "calls", "seconds"):
                totals[k] = totals.get(k, 0) + v
    
    return totals if totals else None


def furnish(d: str, recipe: Dict[str, Any]) -> bool:
    """Furnish the environment for a claim (e.g., install requirements)."""
    env_file = recipe.get("claim", {}).get("environment")
    if not env_file:
        return True
    
    env_path = os.path.join(d, env_file)
    if not os.path.isfile(env_path):
        return False
    
    # Use a cache key based on the requirements file content
    with open(env_path, "rb") as f:
        env_content = f.read()
    cache_key = hashlib.sha256(env_content).hexdigest()
    
    cache_dir = os.path.join(_env_cache_dir(), cache_key)
    venv_dir = os.path.join(d, ".reticuli", "venv")
    
    # Reuse cached environment if available
    if os.path.isdir(cache_dir):
        shutil.copytree(cache_dir, venv_dir)
        return True
    
    # Create a virtual environment
    try:
        subprocess.run(["python3", "-m", "venv", venv_dir], check=True)
        pip = os.path.join(venv_dir, "bin", "pip")
        
        # Install requirements with hashes
        subprocess.run([
            pip, "install", "--require-hashes", "--only-binary=:all:", "-r", env_path
        ], check=True)
        
        # Cache the environment
        shutil.copytree(venv_dir, cache_dir)
        return True
    except Exception:
        return False