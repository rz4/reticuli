"""Pressure from a CONSUMER on realizations of a dependency it relies on.

Every other source asks whether the members behave alike on some input. This
one asks a different and stronger question, the one the substitution finding
showed a dependency's own boundary cannot answer about itself: *does each
realization keep a consumer working?*

The consumer is an ORACLE in the sense the pressure spec reserves the repair
lane for -- an outside standard that can say every member is wrong. It is not
a member of the population and it is not probed differentially; it is a sealed
claim whose gate re-earns, or does not, with each realization substituted for
the dependency's bytes. That verdict, not a behaviour partition, decides the
lane:

  all realizations keep the consumer -> the obligation holds across the whole
      class, and pinning it into the dependency's boundary evicts nobody:
      contraction.
  the realizations split -> the consumer's obligation is the deciding
      criterion; declaring it evicts the realizations that break it: eviction.
  no realization keeps the consumer -> the dependency's boundary is
      universally insufficient for this consumer, a defect in the whole class
      that a pin cannot simply add: repair.

The witness this source exists to reproduce: six blind rebuilds of a config
parser, three from each of two model families, all six passing the parser's
own gate, all six breaking the consumer identically -- agreement between
independent reconstructions is not safety, and only the consumer could expose
the obligation the boundary forgot. That is a repair finding, and the source
emits exactly one pressure to surface it, because the question is single:
which members satisfy this consumer.

This source does not reach the fourth rung and does not claim to. It carries
no foreign silence; it measures the members in hand against a standard this
system wrote. What it reaches is CONTACT when the realizations split -- two
trees that both earned the dependency's root, disagreeing about whether they
are the software a consumer can live with -- which is the third kind, and the
reason an eviction needs the louder signature.
"""

from __future__ import annotations


def pressures(population=None):
    """One pressure: put every realization to the consumer this population names.

    The consumer and the substituted output live on the population registry
    (`population.consumer`), because a consumer pressure is meaningless without
    the population it is paired with -- unlike a specification-derived family,
    which carries its own fixed cases. A population with no consumer named
    yields nothing rather than guessing one.
    """
    if not population or not population.get("consumer"):
        return
    consume = population["consumer"]
    output = population.get("output", "parser.py")
    yield {"schema": "zeta.pressure.1",
           "source": "consumer_surface",
           "id": f"consumer/{output}",
           "clause": "substitutable-under-consumer",
           "simplicity": 0,
           "call": "audit_consumer",
           "args": [consume, output],
           "specified_reader_behaviour":
               "the consumer's own gate re-earns with this realization "
               "substituted for the dependency, or it does not",
           "origin": f"consumer claim {consume}, dependency output {output}"}
