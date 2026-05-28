# MCP SQL Read-Only Server — Key Decisions

## Approach
Each test case provides its own schema and row data inline; the agent loads it into an in-memory SQLite database per request, executes the requested tool calls, and returns structured results — no persistent state needed.

## Read-Only Enforcement
SQL statements are checked by extracting the first keyword and rejecting any that appear in a blocklist (INSERT, UPDATE, DELETE, DROP, CREATE, ALTER, TRUNCATE, etc.) before execution.

## Tool Design
Four tools: `list_tables` (enumerate schema), `describe_table` (columns for one table with not-found error), `run_readonly_query` (safe SELECT with optional LIMIT injection), and `search_schema` (substring match on column names across all tables).

## Result Limiting
If a `limit` arg is provided, a LIMIT clause is appended to the SQL before execution if none exists, or existing LIMIT is replaced — avoiding double-LIMIT bugs.

## No External Dependencies
Pure Python stdlib (json, os, re, sqlite3, pathlib); handles both flat and `{id, input:{...}}` wrapped input formats.
