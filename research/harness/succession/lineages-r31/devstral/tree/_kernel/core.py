"""Core module for computing claim identity and verification."""
import os
import json
import hashlib
import time
import re
from typing import Set, Dict, Any

# Constants
NAMESPACE = "reticuli"
DIGEST = "sha256"
FORMAT = 4
STORE = ".reticuli"
MANIFEST = ".reticuli/manifest.json"
RECIPE = "reticuli.toml"
LEGACY_RECIPE = "claim.toml"
LEDGER = ".reticuli/ledger.jsonl"
USAGE = ".reticuli/usage.json"
MUTATION_RESIDUE = ".reticuli/mutation_score.json"
SIGN_DIR = ".reticuli/mint"
SIGN_NAMESPACE = "reticuli.mint"
_JAILED = "RETICULI_JAILED"
_ENV_CACHE = "RETICULI_ENV_CACHE"
_ENV_CLAIM = "RETICULI_CLAIM"
_ENV_MODEL = "RETICULI_MODEL"
_ENV_OUTPUT = "RETICULI_OUTPUT"
_ENV_OUTPUTS = "RETICULI_OUTPUTS"
_ENV_REQUEST = "RETICULI_REQUEST"
_ENV_SIGNERS = "RETICULI_SIGNERS"
_ENV_TIMEOUT = "RETICULI_GATE_TIMEOUT"
_ENV_TOLERANCE = "RETICULI_TOLERANCE"
_ENV_USAGE = "RETICULI_USAGE"
_ENV_VENDOR = "RETICULI_VENDOR"
_KEEP_ENV = ("PATH", "HOME", "TMPDIR", "LANG", "LC_ALL", "TZ", "RETICULI_JAILED")

# Tuning constants
GATE_TIMEOUT = 120.0
FURNISH_TIMEOUT = 120.0
PRODUCER_TIMEOUT = 120.0
TOLERANCE = 0.1
MUTANT_CEILING = 1.0
MUTANT_FLOOR = 0.1
MUTANT_HEADROOM = 1.0
COST_KEYS = ("usd", "tokens", "calls", "seconds")
COST_LADDER = (1, 10, 100, 1000)
COST_UNITS = ("usd", "tokens", "calls", "seconds")
GUIDANCE_KEYS = ("guidance", "request")
KINDS = frozenset({"produce", "gate"})
_SHELL = "/bin/sh"


class ClaimError(Exception):
    """Exception raised for errors in claim processing."""
    pass


def _now() -> float:
    """Return the current time in seconds since the epoch."""
    return time.time()


def _copy_into(src: str, dst: str) -> None:
    """Copy a file from src to dst."""
    with open(src, "rb") as src_file, open(dst, "wb") as dst_file:
        dst_file.write(src_file.read())


def _judging_host() -> str:
    """Return the judging host name."""
    return "host"


def _safe(base_path: str, name: str) -> str:
    """Resolve a name within the base path, refusing escapes."""
    resolved = os.path.realpath(os.path.join(base_path, name))
    base = os.path.realpath(base_path)
    
    # Debug output
    print(f"Resolved: {resolved}, Base: {base}")
    
    # Check if the resolved path starts with the base path
    if not resolved.startswith(base + os.sep):
        raise ClaimError(f"Path escape attempted: {name}")
    return resolved


def _hash_file(path: str) -> str:
    """Compute the SHA-256 hash of a file."""
    sha256 = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def _write_json(path: str, data: Any) -> None:
    """Write JSON data to a file atomically."""
    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, sort_keys=True)
    os.replace(tmp_path, path)


def canonical_json(data: Any) -> str:
    """Serialize data to canonical JSON."""
    return json.dumps(data, sort_keys=True)


def parse_recipe(recipe_content: str) -> Dict[str, Any]:
    """Parse a TOML recipe without external dependencies."""
    # This is a simplified TOML parser for minimal recipe support
    recipe = {}
    current_section = None
    
    for line in recipe_content.split('\n'):
        line = line.strip()
        
        # Skip empty lines and comments
        if not line or line.startswith('#'):
            continue
            
        # Handle sections
        if line.startswith('[') and line.endswith(']'):
            current_section = line[1:-1]
            if current_section not in recipe:
                recipe[current_section] = {}
            continue
        
        # Parse key-value pairs
        if '=' in line:
            key, value = line.split('=', 1)
            key = key.strip()
            value = value.strip()
            
            # Remove quotes if present
            if value.startswith('"') and value.endswith('"'):
                value = value[1:-1]
            elif value.startswith("'") and value.endswith("'"):
                value = value[1:-1]
            
            # Parse arrays
            if value.startswith('[') and value.endswith(']'):
                value = [v.strip().strip('"') for v in value[1:-1].split(',') if v.strip()]
            
            # Parse numbers
            if value.replace('.', '').isdigit():
                if '.' in value:
                    value = float(value)
                else:
                    value = int(value)
            
            if current_section:
                recipe[current_section][key] = value
            else:
                recipe[key] = value
    
    return recipe


def load_recipe(recipe_path: str) -> Dict[str, Any]:
    """Load and parse a recipe file."""
    with open(recipe_path, "r", encoding="utf-8") as f:
        return parse_recipe(f.read())


def compute_root(recipe: Dict[str, Any], inputs: Set[str], pinned: Set[str], base_path: str) -> str:
    """Compute the root hash of a claim."""
    parts = {"digest": DIGEST, "recipe": canonical_json(recipe)}
    
    for path in inputs:
        safe_path = _safe(base_path, path)
        parts[f"input:{path}"] = _hash_file(safe_path)
    
    for path in pinned:
        safe_path = _safe(base_path, path)
        parts[f"pinned:{path}"] = _hash_file(safe_path)
    
    return hashlib.sha256(canonical_json(parts).encode()).hexdigest()


def build_digest(generated: Set[str], base_path: str) -> str:
    """Compute the build digest of generated files."""
    concatenated = b""
    for path in sorted(generated):
        safe_path = _safe(base_path, path)
        with open(safe_path, "rb") as f:
            concatenated += f.read()
    return hashlib.sha256(concatenated).hexdigest()


def root(recipe_path: str, base_path: str) -> str:
    """Compute the identity hash (root) of a claim."""
    recipe = load_recipe(recipe_path)
    inputs = set(recipe.get("claim", {}).get("inputs", []))
    steps = recipe.get("step", [])
    
    pinned = set()
    generated = set()
    
    for step in steps:
        output = step.get("output")
        if not output:
            continue
        step_class = step.get("class", "pinned")
        if step_class == "generated":
            generated.add(output)
        else:
            pinned.add(output)
    
    return compute_root(recipe, inputs, pinned, base_path)
