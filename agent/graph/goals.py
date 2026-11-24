"""Typed goals (brief 159): the module lives in ``flow/goals.py`` (``flow.trace_v1`` reads it, and a ``flow`` script must not import the agent);
this name keeps the agent-side imports short. See ``flow/goals.py`` for the syntax and the readers."""
from flow.goals import *  # noqa: F401,F403
from flow.goals import ALIAS, EXAMPLE, METRICS, OP_TEXT, OPS, PRIORITIES, Goal, GoalError  # noqa: F401
