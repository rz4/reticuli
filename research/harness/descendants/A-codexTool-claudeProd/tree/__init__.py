"""reticuli — content-addressed software claims.

A claim is a directory holding a recipe, its pinned inputs, and (optionally)
the generated implementation those inputs determine.  Its identity — the
*root* — is a digest over what the claim IS (`spec/identity.md`), never over
any particular implementation of it, so the implementation can be deleted and
regrown without renaming the claim.

The package is layered: `_kernel/` owns identity and verification, `_util.py`
holds the helpers the layers above share, and each outer module adds one
concern (`spec/layers.md`).  Nothing above the kernel imports a kernel
private; the facade `reticuli.kernel` is the kernel's public surface.
"""
__all__ = ["__version__"]

#: The tool's own version, reported by `ret --version`.  Diagnostic only: a
#: claim's identity never depends on which release looked at it.
__version__ = "2.6"
