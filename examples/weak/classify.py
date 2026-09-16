"""Classify a measurement against a threshold. Written by a model, together
with the tests that judge it -- which is the situation this example exists to
illustrate."""


def classify(value):
    if value < 10:
        return "low"
    if value < 100:
        return "medium"
    return "high"
