"""LRCC, the Literature Review Control Center.

Makes the identification and screening stages of a literature review reproducible and
auditable. The package is laid out as a shared hexagon (``domain``, ``ports``, ``adapters``),
one vertical slice per capability under ``features``, and views that decide nothing under
``views`` (ADR-0003). ``tests/test_layering.py`` enforces that layout.
"""
