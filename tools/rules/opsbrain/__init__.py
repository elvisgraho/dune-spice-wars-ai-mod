"""Operations takeover builders (docs/OPERATIONS-PLAN.md).

buying filters purchases using loadouts; casting runs ordered triggers using
slots; agents steers infiltration assignments. ops.py and sdrop.py import the
shared mission policy and scores directly from loadouts.
"""
from rules.opsbrain.casting import build_ops
from rules.opsbrain.buying import build_ops_buy
from rules.opsbrain.agents import build_agent_steer

__all__ = ['build_ops', 'build_ops_buy', 'build_agent_steer']
