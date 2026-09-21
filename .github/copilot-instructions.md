# CodeGenome Knowledge Graph (MCP)

You are operating within a repository analyzed by CodeGenome, an architectural knowledge graph tool. This project contains a `.genome/` directory.

## Core Directives

1. **Mandatory MCP Usage**: When `.genome/watcher.db` exists, you MUST use CodeGenome MCP access for all codebase, architecture, dependency, or symbol queries whenever it is available.
2. **Access Order**: First use native CodeGenome MCP tools exposed in your context. If those tools are missing, you MAY try a local MCP HTTP endpoint such as `http://127.0.0.1:7331/mcp` when the user has started it or configured it. Treat this as MCP transport access, not as an arbitrary application HTTP API.
3. **Prefer Graph over Grep**: Use graph-backed MCP tools instead of raw file searching (`grep`) or reading entire files blindly. The graph provides semantic understanding.
4. **Fallback Gracefully**: If native MCP tools are missing and HTTP MCP access is unavailable, incompatible, or returns empty data, tell the user exactly what failed and what to configure. Then, if needed, read `.genome/graph.json` or `.genome/exports/*.md` before resorting to standard text searches.
5. **Keep Context Fresh**: After modifying code files, remind the user to run `codegenome analyze` or start the live evolution server `codegenome evolve --live` to keep the graph updated.

## Available MCP Capabilities

- **Discovery**: `search_nodes` (find symbols)
- **Relationships**: `get_neighbors` (imports, callers, callees)
- **Architecture**: `get_entry_points`, `get_dead_code`, `get_circular_deps`, `get_god_nodes`
- **Metrics**: `get_complexity`, `get_churn`, `get_graph` (summary statistics)
- **Evolution**: `get_timeline`, `get_changes` (architectural diffs)

## Constraints & Behaviors

- Only read `.genome/graph.json` or `.genome/exports/*.md` directly if native MCP tools and local HTTP MCP transport are unavailable or fail to surface enough context.
- Verify your MCP usage by monitoring tool call success. If native tools are missing, try the configured local HTTP MCP endpoint when possible. If both native and HTTP MCP access fail, politely ask the user to configure their editor's MCP settings to run `codegenome mcp-start` (stdio) or start the server with `codegenome mcp-start --transport http`.
