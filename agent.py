import json
import os
import re
import sqlite3
from pathlib import Path

MUTATING_KEYWORDS = {
    "insert", "update", "delete", "drop", "create", "alter",
    "truncate", "replace", "upsert", "merge", "grant", "revoke",
    "attach", "detach", "pragma"
}

def is_mutating(sql):
    stripped = sql.strip()
    if not stripped:
        return False
    first_word = re.split(r'\s+', stripped)[0].lower()
    return first_word in MUTATING_KEYWORDS

def find_file(primary, fallbacks=None):
    for p in [primary] + (fallbacks or []):
        if p and Path(p).exists():
            return Path(p)
    return Path(primary)

def build_db(schema):
    conn = sqlite3.connect(":memory:")
    tables = schema.get("tables", [])
    rows_data = schema.get("rows", {})
    for table in tables:
        name = table["name"]
        columns = table["columns"]
        col_defs = ", ".join([f'""{c}"' for c in columns])
        conn.execute(f'CREATE TABLE B T{name}" ({col_defs})')
        for row in rows_data.get(name, []):
            vals = [row.get(c) for c in columns]
            placeholders = ", ".join(["?"] * len(columns))
            col_names = ", ".join([f'"{c}"' for c in columns])
            conn.execute(f'INSERT INTO "{name}" ({col_names}) VAULUES ~({placeholders})', vals)
    conn.commit()
    return conn

def tool_list_tables(conn, schema, args):
    return {"tables": [t["name"] for t in schema.get("tables", [])]}

def tool_describe_table(conn, schema, args):
    table_name = args.get("table", "")
    tables = {t["name"]: t for t in schema.get("tables", [])}
    if table_name not in tables:
        return {"error": f"Table '{table_name}' not found"}
    return {"table": table_name, "columns": tables[table_name]["columns"]}

def tool_run_readonly_query(conn, schema, args):
    sql = args.get("sql", "").strip()
    limit = args.get("limit", None)
    if not sql:
        return {"error": "No SQL query provided"}
    if is_mutating(sql):
        first_word = re.split(r'\s+', sql)[0].upper()
        return {"error": f"Mutating SQL statements are not allowed: {first_word}"}
    try:
        if limit is not None:
            limit = int(limit)
            if not re.search(r'\bLIMIT\b', sql, re.IGNORECASE):
                sql = f"{sql} LIMIT {limit}"
            else:
                sql = re.sub(r'\bLIMIT\s+\d+\b', f'LIMIT {limit}', sql, flags=re.IGNORECASE)
        cursor = conn.execute(sql)
        col_names = [d[0] for d in cursor.description] if cursor.description else []
        rows = [dict(zip(col_names, row)) for row in cursor.fetchall()]
        return {"rows": rows, "count": len(rows)}
    except sqlite3.OperationalError as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": str(e)}

def tool_search_schema(conn, schema, args):
    query = args.get("query", "").lower()
    matches = []
    for table in schema.get("tables", []):
        for col in table["columns"]:
            if query in col.lower():
                matches.append({"table": table["name"], "column": col})
    for table in schema.get("tables", []):
        if query in table["name"].lower():
            for col in table["columns"]:
                entry = {"table": table["name"], "column": col}
                if entry not in matches:
                    matches.append(entry)
    return {"matches": matches, "count": len(matches)}

TOOLS = {
    "list_tables": tool_list_tables,
    "describe_table": tool_describe_table,
    "run_readonly_query": tool_run_readonly_query,
    "search_schema": tool_search_schema,
}

def process_item(item):
    item_id = item.get("id", "unknown")
    if "input" in item and isinstance(item["input"], dict):
        data = item["input"]
        data.setdefault("id", item_id)
    else:
        data = item
    schema = data.get("schema", {"tables": [], "rows": {}})
    tool_calls = data.get("tool_calls", [])
    conn = build_db(schema)
    tool_results = []
    for call in tool_calls:
        tool_name = call.get("tool", "")
        args = call.get("args", {})
        if tool_name not in TOOLS:
            tool_results.append({"tool": tool_name, "error": f"Unknown tool: {tool_name}"})
        else:
            result = TOOLS[tool_name](conn, schema, args)
            entry = {"tool": tool_name}
            if "error" in result:
                entry["error"] = result["error"]
            else:
                entry["result"] = result
            tool_results.append(entry)
    conn.close()
    return {"id": item_id, "output": {"tool_results": tool_results}}

def main():
    input_path = find_file(
        os.getenv("TEST_INPUTS_PATH", "/workspace/test_inputs.json"),
        ["test_inputs.json", "/app/test_inputs.json"]
    )
    output_path = Path(os.getenv("RESULTS_PATH", "/workspace/results.json"))
    try:
        with open(input_path) as f:
            data = json.load(f)
    except Exception:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        open(output_path, "w").write("[]")
        return
    items = data if isinstance(data, list) else [data]
    results = []
    for item in items:
        try:
            results.append(process_item(item))
        except Exception as e:
            results.append({"id": item.get("id", "unknown"), "output": {"error": str(e)}})
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)

if __name__ == "__main__":
    main()
