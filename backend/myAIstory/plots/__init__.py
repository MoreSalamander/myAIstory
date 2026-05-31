"""PlotKit — the curated, theme-agnostic plot grab bag (ARCHITECTURE / SPEC).

A human-owned catalog of structural beat *shapes* the arc planner adapts to a
series' cast and theme. Like the verify/ package, the sound library, and the
voice registry, selection here is a pure lookup — no LLM, no network. A plot
shape is an offered scaffold, not model output: the model only specializes it
to the theme, which keeps even an exotic theme from collapsing the arc.
"""

from myAIstory.plots.kit import Plot, PlotKit

__all__ = ["Plot", "PlotKit"]
