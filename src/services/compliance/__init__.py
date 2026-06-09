"""Compliance engine.

Handbook-sourced rules, each toggleable off/warn/enforce (default warn; enforce
is opt-in). `rules.py` holds the registry + evaluators; `engine.py` resolves
each rule's mode from `compliance_settings` and produces graded findings.
"""
