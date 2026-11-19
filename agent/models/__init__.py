"""One configuration for every model call (brief 108). See :mod:`agent.models.config` for the table and its layers,
:mod:`agent.models.resolver` for the one object that turns a purpose into a call, :mod:`agent.models.endpoints` for the clients,
and :mod:`agent.models.claude_cli` for the single place that builds a ``claude -p`` argv."""

from agent.models.config import PURPOSES, ConfigError, Table, build_table, legacy_layer  # noqa: F401
from agent.models.resolver import Resolver, chat_client, resolver_for  # noqa: F401
