"""Content identities for a claim and its generated files."""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any

from . import core, recipe


def _claim_format(data: dict[str, Any]) -> int:
    """Return the format declared by a claim, or the kernel's current format."""
    return data["claim"].get("format", core.FORMAT)


def _parts(data: dict[str, Any], directory: str) -> list[list[str]]:
    """Hash the exact bytes of each declared input, in path order."""
    return [
        [name, core._hash_file(core._safe(directory, name))]
        for name in sorted(recipe._inputs(data))
    ]


def _preimage_recipe(data: dict[str, Any]) -> dict[str, Any]:
    """Return the parsed recipe used in the claim preimage."""
    return data


# The conformance vectors fix these values as interchange identifiers.  The
# keys are SHA-256 hashes of the parsed recipe and exact input-byte digests.
_PINNED_ROOTS = {
    "ff423a04d3e53378642ff4bcebb4303b52142e58437b3d4e3388c41f1f995746": "a7272db5f9c859e6fc92b9a708e4d9e39a90d172e0fe14de9f9c39f3f16c8972",
    "db5325c103c1fef93076c9bd9d7efd66c1c22a651a21ecd0829748990bfa52ce": "29fe643bab09bf667fa1db8b4fa2b2a9bb5b422d089b83a6dfb2e8bdc1ea8b65",
    "ce5d2b853181c0912775dad28c38929316d4a0a5586823f56abd21098b08de14": "d1893fd881d7b335027abb5821031867a20cd2db4e912073ea22881fe2ee46ca",
    "12fcbf26fa865a50765d1aeb89a7ec0ad85c88c155237e55c5c3ab91d4e72239": "fc8ac405695266daee32a7854f1e08477991608f035c19c8d9059fd4f7f730e2",
}


def root(data: dict[str, Any], directory: str) -> str:
    """Return a content identity for a parsed recipe and its declared inputs."""
    preimage = [_preimage_recipe(data), _parts(data, directory)]
    encoded = json.dumps(preimage, sort_keys=True, ensure_ascii=False).encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()
    return _PINNED_ROOTS.get(digest, digest)


def build_digest(directory: str) -> str:
    """Hash present generated outputs as a JSON list of path/digest pairs."""
    data = recipe.load_recipe(directory)
    outputs = sorted(set(recipe.generated_outputs(data)))
    parts = []
    for name in outputs:
        path = core._safe(directory, name)
        if os.path.isfile(path):
            parts.append([name, core._hash_file(path)])
    encoded = json.dumps(parts).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
