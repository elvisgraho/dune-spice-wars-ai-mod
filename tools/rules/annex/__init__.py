"""Annex and siege-target scoring builders.

scoring owns candidate eligibility and wrapper installation; valuation owns the
Annex-only value calculation. Dependencies point from scoring to valuation.
"""
from rules.annex.scoring import build_supply_block, build_scoring

__all__ = ['build_supply_block', 'build_scoring']
