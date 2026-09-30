"""reticuli._cli -- the human/machine surface: the `--json` envelope and
the claim-reading views the `ret` command line prints from.

`output` owns the envelope shape and the one-voice error line; `views`
turns a claim directory into the documented state dict and the `next`
ladder. Neither module runs a gate or writes to a claim -- both are pure
readers over what `reticuli.kernel` already computes.

Stdlib only. Never the network.
"""
