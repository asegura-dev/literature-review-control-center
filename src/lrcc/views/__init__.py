"""Views parse input and render output; they decide nothing (ADR-0003).

A view imports features. It imports adapters only in composition code, where the view, as the
driving adapter, builds concrete adapters from the configuration and hands them to a feature.
"""
