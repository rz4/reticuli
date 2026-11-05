"""reticuli -- record and reproduce software claims.

A claim is a directory holding a recipe, its pinned inputs, and (optionally)
its generated outputs. Its identity is a hash over what the claim IS -- the
criteria -- never over any particular implementation of it. See spec/.

The layers (spec/layers.md) are plain modules in this package: the kernel
(identity and verification), exchange, authoring, agents, launcher, and the
surface. Nothing above the kernel imports a kernel private; `_util` holds
what the layers share.
"""
__version__ = "2.6"
VERSION = __version__
