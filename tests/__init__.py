"""Test package root.

Marks ``tests`` as a regular package so that ``from tests.integration.conftest
import ...`` resolves consistently across pytest invocation styles (bare
``pytest`` vs ``python -m pytest``) and CI environments. Without this file
``tests`` is only an implicit namespace package, which left the repo root off
``sys.path`` under some import modes and produced
``ModuleNotFoundError: No module named 'tests.integration'`` during collection.
"""
