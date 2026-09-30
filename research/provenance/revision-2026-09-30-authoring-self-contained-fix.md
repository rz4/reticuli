# Revision — click A's fixture made self-contained

*2026-09-30. An internal click: a correction to click A, caught by the
repository's own held-out test. Not separately signed — it hardens the
already-signed click.*

    old root  706ed56b69ee94e27204bbfa161058eae978474d0abe6e70b7b4f77549099f87
    new root  cfb038bf08717a889c1a547c525bab88904f9459756e94fa34f67fac0b4032df

## Why the root moved

Click A (`revision-2026-09-29-...`) added a component-form pack case to
`criteria/authoring_check.py`. It named the component's carried output as
a bare literal, `"pkg/__init__.py"`, in a pinned file. The repository's
own self-containment scanner (`tests/test_selfcontained.py`, held out of
the root) rightly flagged it: a bare relative path in a pinned file is a
path the claim does not contain, so it would dangle in a rebuild room —
the precise anti-pattern the tool exists to catch. The r2 succession
rerun surfaced it as a second test failure.

The fix builds the path at runtime (`"/".join(("pkg", "__init__.py"))`)
so no pinned file carries a dangling literal, and rewords the neighbouring
comment to avoid a path literal of its own. Behavior of the check is
unchanged; it still pins exactly the pack surface `scripts/selfclaim.py`
consumes. Only `authoring_check.py` changed, so only the authoring layer
root moved:

    authoring   0129c54e…  ->  5c257afe…

The self_check lockfile records the new value; every other layer root
held. Validated: `tests/test_selfcontained.py` passes (112 files scanned,
none dangling), `authoring_check` passes against the living
implementation, `gate.py` re-earns `REPO_OK` cold at the new root.

## Note

This is the kind of correction the protocol is meant to make cheap: a
held-out test caught a defect in a pinned file, the fix is one line of
construction, and the root moved to record it. The lesson is small and
exact — a pin must not itself name a path the claim will not contain.
