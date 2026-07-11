#!/usr/bin/env python3

"""
Discovery system integrations.
"""

from systems.primo import PrimoSystem
from systems.vufind import VuFindSystem

__all__ = ["VuFindSystem", "PrimoSystem"]
