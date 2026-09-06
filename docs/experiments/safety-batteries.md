# Completing the safety body — filesystem adversary and crypto ceremony

The reach-the-jester plan has three bodies (docs/notes/jester.md): fidelity,
safety, proof. Fidelity and proof were carried far; this closes the two named
surfaces the safety body still had open — the reviewer's rung-4 (filesystem
adversary) and rung-5 (cryptographic ceremony). Each was **probed first** (find
the real hole, not the imagined one), then carved with a pin.

## Rung 4 — the bytes boundary (`_hf`)

`_safe` is the one PATH boundary; it refuses absolute paths, `..` climbs, and
out-of-root symlinks. But confinement is also a *bytes* question a path check
cannot answer, and the probe found one real hole among several near-misses:

| adversary | before | mechanism |
|---|---|---|
| **hardlink seed → outside inode** | **SEALED foreign bytes** | path stays inside root; `_safe` sees a local name; `_hf` reads the outside inode's content |
| FIFO / named pipe | refused (by luck of `open`) | read would block — a claim-path DoS |
| symlink → device | refused | already carved (escapes root) |
| directory as file | refused | `open` errors |

The hardlink is the exfiltration `_safe` *promises* to prevent, leaking through
because a hardlink shares an inode without redirecting its path. The carve makes
`_hf` the one BYTES boundary, mirroring `_safe`: a declared file must be a
**regular file with a single link** (`S_ISREG` and `st_nlink == 1`). That closes
the hardlink (nlink > 1 betrays the second name), and closes FIFO/device/
directory *robustly and cross-platform* rather than relying on `open` happening
to error. Honest records write their own seeds, so nlink == 1 holds for every
legitimate file — the self-host reseals unchanged. kernel-core moved
`7c31e5a3 → 3e81802c`; the other seven held.

## Rung 5 — domain separation of the mint signature (confused deputy)

The probe found the ceremony sound in the ways already carved (packet binding,
realization-digest binding, trusted-anchor requirement, drift demotion — see the
solid-lifecycle clauses) but with one latent hole: **attestation and mint signed
in the same ssh namespace** (`"reticuli"`). An attestation says "this ran on my
machine"; a mint says "I authorize this as solid" — different acts, different
stakes. Sharing a namespace meant they were separated only by *file shape*
(defense by accident); an attestation signature over content an attacker arranged
to also parse as a mint statement would be a confused deputy.

The carve gives the mint its own signature domain, `MINT_NAMESPACE =
"reticuli.mint"`: `mint`, `mint_check`, and the kernel's `minted()` all sign and
verify there, while attestation stays in `"reticuli"`. A signature made in one
namespace **cannot** verify in the other — the purposes are cryptographically
disjoint, not merely distinguishable. Zero blast radius (no committed mint
artifacts; the repo is liquid by choice). kernel-core moved
`3e81802c → 75589657`; the other seven held (the attestation code is free at the
exchange layer, so its root did not move).

The pin has teeth: the solid record's mint statement re-signed under the
attestation namespace demotes to **liquid**; re-signed under the mint namespace
it is **solid** again — separation, not breakage.

## What this does and does not finish

Closed, and regeneration will confirm at the next self-host: hardlink/FIFO/
device/directory exfiltration and DoS through the read path; confused-deputy
between attestation and mint.

Not attempted here, and named honestly as the remaining rung-5 depth: **key
rotation, revocation lists, and validity windows.** ssh allowed-signers supports
`valid-after`/`valid-before` and `-Overify-time`, and `ssh-keygen -Y` supports a
revocation file; `minted()` uses none of them, so a compromised key cannot yet be
revoked and a mint cannot yet be time-boxed. That is a feature surface (a
revocation/validity policy), not a one-line hole, and it is the natural next
crypto step whenever the ceremony needs to survive a key's lifecycle. Threshold
(M-of-N) authorization is likewise a feature, not a bug: `minted()` is `any`
trusted statement, correct for a single-verifier model.

## Status

Probed and carved 2026-09-06, no model calls. kernel-core `75589657`; checks
pass bare and jailed; 48 tests green; self-host reseals. Two of the safety body's
named surfaces are closed; the rotation/revocation surface is documented as the
remaining depth.
