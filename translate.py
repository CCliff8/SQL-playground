"""Snowflake -> PostgreSQL translator (stdin: SQL, stdout: JSON). Uses sqlglot from .venv."""
import json, re, sys, sqlglot
from sqlglot import exp
sql = sys.stdin.read()
try:
    stmts = []
    for pg in sqlglot.transpile(sql, read="snowflake", write="postgres"):
        # Snowflake `col:key::string` / `col:key = 'x'` yield unquoted text; Postgres needs the *_TEXT variant for that
        pg = re.sub(r"CAST\(JSON_EXTRACT_PATH\(([^()]*)\) AS (?:TEXT|VARCHAR)\)", r"JSON_EXTRACT_PATH_TEXT(\1)", pg)
        pg = re.sub(r"JSON_EXTRACT_PATH\(([^()]*)\)(\s*(?:=|<>|!=|IN|LIKE|ILIKE)\s)", r"JSON_EXTRACT_PATH_TEXT(\1)\2", pg)
        pg = pg.replace("JSON_EXTRACT_PATH_TEXT(", "JSONB_EXTRACT_PATH_TEXT(").replace("JSON_EXTRACT_PATH(", "JSONB_EXTRACT_PATH(")  # columns are jsonb
        tree = sqlglot.parse_one(pg, read="postgres")
        sub = tree.args.get("from_") or tree.args.get("from") if isinstance(tree, exp.Select) else None
        sub = sub.this if sub is not None else None
        # QUALIFY becomes a subquery; LIMIT/OFFSET must apply after its filter, i.e. on the outer query
        if isinstance(sub, exp.Subquery) and sub.alias == "_t" and isinstance(sub.this, exp.Select):
            for k in ("limit", "offset"):
                if sub.this.args.get(k):
                    tree.set(k, sub.this.args.pop(k))
        stmts.append(tree.sql(dialect="postgres", pretty=True))
    out = ";\n".join(stmts)
    print(json.dumps({"sql": out}))
except Exception as e:
    print(json.dumps({"error": str(e).split("\n")[0]}))
