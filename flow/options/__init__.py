"""Strategy options (brief 104): analyse a loaded design, then offer two to four ways to improve it before anything is changed.

``analysis`` reads existing records (read-only); ``schema`` classifies the request, validates what the options generator
returns and computes the fields a model must not set (scope command, cost, what is not touched, boundary flags); ``generate``
makes the one model call (purpose ``options`` of the model table, prompt in the private knowledge repository) and records it.
See ``docs/strategy_options.md``.
"""
