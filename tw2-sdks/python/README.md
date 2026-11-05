The Triggerware Python SDK is an asynchronous Python client for a Triggerware server. It exposes Triggerware's tables, tools, queries, triggers, agents, connectors, runtimes, configuration, logging, cursors, and system operations as typed Python methods. Use it to communicate with Triggerware without manually constructing JSON-RPC requests. It also provides typed resource definitions and asynchronous helpers for streamed query results and trigger notifications.

By default, a locally running Triggerware server accepts TCP SDK connections at `localhost:5221`.

1. `TriggerwareClient(peer: rpc.Peer) -> None`

   This is used for creating a client around an existing JSON-RPC peer and exposing each Triggerware resource service.

2. `async TriggerwareClient.connect_tcp(address: str) -> Self`

   This is used for connecting to a Triggerware server over TCP and returning a ready client. Use `localhost:5221` for the default local server.

3. `async TriggerwareClient.connect_ws(url: str, api_key: str) -> Self`

   This is used for connecting to a Triggerware server over WebSocket, authorizing with an API key, and returning a ready client.

4. `async TriggerwareClient.mcp(method: str, params: dict[str, Any] | None = None) -> Any`

   This is used for forwarding an MCP method and optional parameters through Triggerware's MCP JSON-RPC endpoint.

5. `async client.configuration.get() -> Configuration`

   This is used for retrieving the current Triggerware configuration without the agent API key.

6. `async client.configuration.set(*, default_timeout_ms: int | None = None, default_batch_size: int | None = None, default_trigger_batch_size: int | None = None, agent_provider: str | None = None, agent_model: str | None = None, agent_api_key: str | None = None, max_log_file_size: str | None = None, secure: bool = False) -> Configuration | Authorization`

   This is used for updating supplied configuration fields or starting the secure browser configuration flow.

7. `async client.configuration.refresh() -> Configuration`

   This is used for reloading Triggerware's configuration from disk and returning the refreshed values.

8. `async client.agents.create(name: str | None = None, *, prompt: str | None = None, meta: AgentMetadata | None = None, instructions: str | None = None) -> Agent`

   This is used for creating an agent from an explicit definition or an agent-creator prompt.

9. `async client.agents.get(name: str | list[str]) -> Agent | list[Agent]`

   This is used for retrieving one or more agent definitions.

10. `async client.agents.update(name: str, *, prompt: str | None = None, meta: AgentMetadata | None = None, instructions: str | None = None) -> Agent`

    This is used for updating an existing agent directly or through an agent-creator prompt.

11. `async client.agents.list() -> list[str]`

    This is used for listing all registered agent names.

12. `async client.agents.delete(name: str | list[str]) -> None`

    This is used for deleting one or more agents.

13. `async client.agents.run(name: str, data: dict[str, Any]) -> dict[str, Any]`

    This is used for manually running an agent with input data and returning its structured result.

14. `async client.agents.sync(*, agents: list[str] | None = None, connectors: list[str] | None = None) -> None`

    This is used for reconciling agent definitions on disk with the agents registered in Triggerware.

15. `async client.tables.create(name: str | None = None, *, prompt: str | None = None, code: str | None = None, meta: TableMetadata | None = None, runtime: TableRuntime | None = None) -> Table`

    This is used for creating a table from an explicit definition or a table-creator prompt.

16. `async client.tables.get(name: str | list[str]) -> Table | list[Table]`

    This is used for retrieving one or more table definitions and their configuration status.

17. `async client.tables.update(name: str, *, prompt: str | None = None, code: str | None = None, meta: TableMetadata | None = None, runtime: TableRuntime | None = None) -> Table`

    This is used for updating a standalone table directly or through a table-creator prompt.

18. `async client.tables.list() -> list[str]`

    This is used for listing all registered table names.

19. `async client.tables.delete(name: str | list[str]) -> None`

    This is used for deleting one or more standalone tables.

20. `async client.tables.sync(*, tables: list[str] | None = None, connectors: list[str] | None = None) -> None`

    This is used for reconciling table definitions on disk with the tables registered in Triggerware.

21. `async client.tables.configure(name: str, config: dict[str, Any] | None = None, *, secure: bool = False) -> Authorization`

    This is used for configuring a standalone table directly or starting its secure configuration flow.

22. `Cursor(peer: rpc.Peer, *, cursor: str, sql: str, signature: list[CursorColumn], rows: list[list[Any]], exhausted: bool) -> None`

    This is used for representing an open Triggerware cursor and its current buffered rows and execution state.

23. `async Cursor.fetch() -> list[list[Any]]`

    This is used for fetching the next batch of rows from an open cursor.

24. `async Cursor.close() -> None`

    This is used for closing a cursor and releasing its server-side execution state.

25. `Cursor.__aiter__() -> Cursor`

    This is used for beginning asynchronous iteration over a cursor's buffered and future rows.

26. `async Cursor.__anext__() -> list[Any]`

    This is used for returning the next cursor row during asynchronous iteration.

27. `async client.cursors.open(*, sql: str | None = None, prompt: str | None = None, batch_size: int | None = None, timeout_ms: int | None = None) -> Cursor`

    This is used for opening a cursor from exactly one SQL query or natural-language prompt.

28. `async client.connectors.install(*, name: str | None = None, url: str | None = None, tag: str | None = None, config: dict[str, Any] | None = None, secure: bool = False) -> Authorization`

    This is used for installing a connector from the catalog or a Git repository, with optional tagging and configuration.

29. `async client.connectors.get(name: str | list[str], *, tag: str | None = None) -> Connector | list[Connector]`

    This is used for retrieving one or more installed connectors and their tables, tools, agents, and configuration.

30. `async client.connectors.list() -> list[str]`

    This is used for listing all installed connector names.

31. `async client.connectors.configure(name: str, *, tag: str | None = None, config: dict[str, Any] | None = None, secure: bool = False) -> Authorization`

    This is used for configuring an installed connector directly or starting its secure configuration flow.

32. `async client.connectors.authorize(name: str, *, tag: str | None = None) -> str`

    This is used for starting OAuth authorization for a connector and returning its authorization URL.

33. `async client.connectors.catalog() -> list[ConnectorCatalogEntry]`

    This is used for retrieving the maintained connector catalog.

34. `async client.connectors.describe(*, name: str | None = None, url: str | None = None) -> ConnectorDescription`

    This is used for inspecting a catalog connector or public Git repository without installing it.

35. `async client.connectors.uninstall(name: str | list[str], *, tag: str | None = None) -> None`

    This is used for uninstalling one or more connectors and their registered resources.

36. `async client.logging.set(level: LogLevel) -> None`

    This is used for changing the minimum runtime log level for new Triggerware log entries.

37. `Query(peer: rpc.Peer, definition: QueryDefinition) -> None`

    This is used for representing a saved query and its local definition, buffered rows, and fetch state.

38. `async Query.reset() -> None`

    This is used for resetting a saved query's server-side cursor and refreshing its local definition.

39. `async Query.fetch(*, params: list[QueryParameterValue] | None = None, rows: int | None = None) -> list[list[Any]]`

    This is used for fetching the next rows from a saved query with optional parameter values and row-count override.

40. `Query.__aiter__() -> Query`

    This is used for beginning asynchronous iteration over a saved query's buffered and future rows.

41. `async Query.__anext__() -> list[Any]`

    This is used for returning the next saved-query row during asynchronous iteration.

42. `async client.queries.create(name: str | None = None, *, description: str | None = None, sql: str | None = None, prompt: str | None = None, params: list[QueryParameter] | None = None, batch_size: int | None = None, timeout_ms: int | None = None) -> Query`

    This is used for creating a saved query from an explicit definition or a query-creator prompt.

43. `async client.queries.convert(name: str, *, trigger_name: str | None = None, prompt: str | None = None, params: list[QueryParameterValue] | None = None, schedule: str | None = None, batch_size: int | None = None, timeout_ms: int | None = None, report_noops: bool | None = None, enabled: bool | None = None) -> QueryFetch`

    This is used for converting a saved query into a trigger without resupplying its SQL.

44. `async client.queries.get(name: str | list[str]) -> Query | list[Query]`

    This is used for retrieving one or more saved queries as stateful query objects.

45. `async client.queries.delete(name: str | list[str]) -> None`

    This is used for deleting one or more saved queries.

46. `async client.queries.list() -> list[str]`

    This is used for listing all saved query names.

47. `async client.runtimes.list() -> list[str]`

    This is used for listing installed external runtimes.

48. `async client.runtimes.install(name: Runtime) -> None`

    This is used for installing the selected Python or Node runtime.

49. `async client.runtimes.uninstall(name: Runtime) -> None`

    This is used for uninstalling the selected external runtime.

50. `async client.system.health() -> Health`

    This is used for checking whether the Triggerware server is healthy enough to accept requests.

51. `async client.system.update() -> SystemUpdate`

    This is used for updating the local Triggerware installation and reporting the replaced artifacts and restart requirement.

52. `async client.system.authorize(api_key: str) -> bool`

    This is used for authorizing the current connection with an API key.

53. `async client.system.authorized() -> bool`

    This is used for checking whether the current connection is authorized.

54. `async client.tools.create(name: str | None = None, *, prompt: str | None = None, code: str | None = None, meta: ToolMetadata | None = None, runtime: ToolRuntime | None = None) -> Tool`

    This is used for creating a standalone tool from an explicit definition or a tool-creator prompt.

55. `async client.tools.get(name: str | list[str]) -> Tool | list[Tool]`

    This is used for retrieving one or more tool definitions and their configuration status.

56. `async client.tools.update(name: str, *, prompt: str | None = None, code: str | None = None, meta: ToolMetadata | None = None, runtime: ToolRuntime | None = None) -> Tool`

    This is used for updating a standalone tool directly or through a tool-creator prompt.

57. `async client.tools.list() -> list[str]`

    This is used for listing all registered tool names.

58. `async client.tools.delete(name: str | list[str]) -> None`

    This is used for deleting one or more standalone tools.

59. `async client.tools.sync(*, tools: list[str] | None = None, connectors: list[str] | None = None) -> None`

    This is used for reconciling tool definitions on disk with the tools registered in Triggerware.

60. `async client.tools.configure(name: str, config: dict[str, Any] | None = None, *, secure: bool = False) -> Authorization`

    This is used for configuring a standalone tool directly or starting its secure configuration flow.

61. `async client.triggers.create(name: str | None = None, *, description: str | None = None, sql: str | None = None, prompt: str | None = None, schedule: str | None = None, batch_size: int | None = None, timeout_ms: int | None = None, report_noops: bool | None = None, enabled: bool | None = None) -> Trigger`

    This is used for creating a trigger from an explicit definition or a trigger-creator prompt.

62. `async client.triggers.get(name: str | list[str]) -> Trigger | list[Trigger]`

    This is used for retrieving one or more trigger definitions.

63. `async client.triggers.update(name: str, *, description: str | None = None, sql: str | None = None, prompt: str | None = None, schedule: str | None = None, batch_size: int | None = None, timeout_ms: int | None = None, report_noops: bool | None = None, enabled: bool | None = None) -> Trigger`

    This is used for updating an existing trigger directly or through a trigger-creator prompt.

64. `async client.triggers.list() -> list[str]`

    This is used for listing all registered trigger names.

65. `async client.triggers.delete(name: str | list[str]) -> None`

    This is used for deleting one or more triggers.

66. `async client.triggers.enable(name: str) -> None`

    This is used for enabling scheduled execution for a trigger.

67. `async client.triggers.disable(name: str) -> None`

    This is used for disabling scheduled execution for a trigger.

68. `async client.triggers.run(name: str, *, batch_size: int | None = None, timeout_ms: int | None = None) -> TriggerDelta`

    This is used for running a trigger immediately and returning its added and deleted rows.

69. `async client.triggers.poll(name: str) -> list[TriggerDelta]`

    This is used for draining and returning a trigger's cached deltas.

70. `async client.triggers.watch(name: str, callback: TriggerCallback, *, resume_window_ms: int | None = None) -> str`

    This is used for subscribing a callback to retained and future trigger deltas and returning a resume token.

71. `async client.triggers.resume(name: str, resume_token: str, callback: TriggerCallback, *, resume_window_ms: int | None = None) -> str`

    This is used for resuming trigger notifications from a valid token and returning the active resume token.

72. `async client.triggers.unwatch(*, name: str | None = None, resume_token: str | None = None) -> None`

    This is used for stopping a trigger subscription by trigger name or resume token.
