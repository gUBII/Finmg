"""Modular NSWTG artifact engine.

Fills any NSWTG AcroForm PDF from the DB via a declarative JSON field map
(`src/config/artifacts/<key>.json`) + a small registry of parameterised
resolvers. See `spec.py` (load), `resolvers.py` (registry), `fill.py` (render).
"""
