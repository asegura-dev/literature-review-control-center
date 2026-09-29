"""One vertical slice per capability, each holding its own use case (ADR-0003).

A feature receives its adapters and never constructs them. It imports ``domain`` and ``ports``
only, never ``adapters`` and never another feature: logic two features need moves into
``domain``.
"""
