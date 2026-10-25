import os
import ast
import json
import hashlib
import duckdb
import requests
from datetime import datetime, timezone

DB_FILE = "data/code_skeleton.db"
HISTORY_DIR = "data/history"
EXPORT_DIR = "public"
API_DIR = os.path.join(EXPORT_DIR, "v1")
SKELETON_DIR = os.path.join(API_DIR, "skeletons")

# Core agent-facing libraries frequently ingested into coding prompts
TARGET_SOURCES = {
    "requests_api": "https://raw.githubusercontent.com/psf/requests/main/src/requests/api.py",
    "requests_sessions": "https://raw.githubusercontent.com/psf/requests/main/src/requests/sessions.py",
    "fastapi_applications": "https://raw.githubusercontent.com/fastapi/fastapi/master/fastapi/applications.py",
    "fastapi_routing": "https://raw.githubusercontent.com/fastapi/fastapi/master/fastapi/routing.py",
    "httpx_client": "https://raw.githubusercontent.com/encode/httpx/master/httpx/_client.py",
    "pydantic_main": "https://raw.githubusercontent.com/pydantic/pydantic/main/pydantic/main.py"
}

class ASTSkeletonizer(ast.NodeTransformer):
    """Strips all implementation bodies while retaining imports, classes, and method signatures."""
    def visit_FunctionDef(self, node):
        return self._prune_function(node)

    def visit_AsyncFunctionDef(self, node):
        return self._prune_function(node)

    def _prune_function(self, node):
        # Retain docstring if present, replace remainder of execution body with Ellipsis (...)
        docstring = ast.get_docstring(node)
        new_body = []
        if docstring:
            new_body.append(ast.Expr(value=ast.Constant(value=docstring.strip()[:150])))
        new_body.append(ast.Expr(value=ast.Constant(value=Ellipsis)))
        node.body = new_body
        return node

def compute_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def extract_skeleton(source_code: str) -> str:
    try:
        tree = ast.parse(source_code)
        transformer = ASTSkeletonizer()
        pruned_tree = transformer.visit(tree)
        ast.fix_missing_locations(pruned_tree)
        return ast.unparse(pruned_tree)
    except Exception as e:
        print(f"AST parse error: {e}")
        return ""

def build_static_api(conn):
    os.makedirs(SKELETON_DIR, exist_ok=True)
    now_iso = datetime.now(timezone.utc).isoformat()

    cur = conn.execute("SELECT package_name, original_size_bytes, skeleton_size_bytes, token_reduction_pct, last_updated_utc, skeleton_code FROM package_skeletons")
    rows = cur.fetchall()

    catalog = []
    lines = [
        "# Code AST Skeleton Wire",
        f"> Last Sync: {now_iso} UTC",
        "> Optimization: Implementation bodies pruned via Python AST (Avg 80-90% token savings).",
        "",
        "## Available Code Structural Skeletons"
    ]

    for row in rows:
        pkg_name, orig_sz, skel_sz, reduction, updated, code = row
        catalog.append({
            "target": pkg_name,
            "original_bytes": orig_sz,
            "skeleton_bytes": skel_sz,
            "token_reduction_pct": round(reduction, 2),
            "updated_utc": updated,
            "endpoint": f"v1/skeletons/{pkg_name}.py"
        })

        with open(os.path.join(SKELETON_DIR, f"{pkg_name}.py"), "w", encoding="utf-8") as f:
            f.write(code)

        lines.append(f"- **{pkg_name}**: {reduction:.1f}% reduction ({orig_sz // 1024} KB -> {skel_sz // 1024} KB) | Endpoint: `v1/skeletons/{pkg_name}.py`")

    with open(os.path.join(API_DIR, "index.json"), "w", encoding="utf-8") as f:
        json.dump({"metadata": {"updated_at": now_iso, "count": len(catalog)}, "targets": catalog}, f, indent=2)

    with open(os.path.join(EXPORT_DIR, "llms.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    html = f"""<!DOCTYPE html><html><head><title>Code AST Skeleton Wire</title></head>
    <body style='font-family:system-ui,sans-serif;max-width:850px;margin:2rem auto;line-height:1.6;padding:0 1rem;'>
    <h1>🧬 Code AST Skeleton Wire</h1>
    <p>Structural Python signatures, classes, and method interfaces with execution logic stripped for LLMs.</p>
    <h3>Machine Feeds</h3>
    <ul>
      <li><a href='v1/index.json'>/v1/index.json</a> (Catalog &amp; Token Metrics)</li>
      <li><a href='llms.txt'>llms.txt</a> (Token-Efficient Digest)</li>
      <li><a href='skeletons.parquet'>skeletons.parquet</a> (Columnar Parquet Snapshot)</li>
    </ul>
    <h3>Extracted Skeletons</h3>
    <ul>
      {"".join([f"<li><a href='v1/skeletons/{c['target']}.py'>{c['target']}.py</a> ({c['token_reduction_pct']}% smaller)</li>" for c in catalog])}
    </ul>
    </body></html>"""
    with open(os.path.join(EXPORT_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)

def run():
    os.makedirs("data", exist_ok=True)
    os.makedirs(HISTORY_DIR, exist_ok=True)
    os.makedirs(EXPORT_DIR, exist_ok=True)

    conn = duckdb.connect(DB_FILE)
    with open("schema.sql", "r", encoding="utf-8") as f:
        conn.execute(f.read())

    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    date_str = now.strftime("%Y-%m-%d")
    year_str = now.strftime("%Y")
    month_str = now.strftime("%m")

    month_dir = os.path.join(HISTORY_DIR, year_str, month_str)
    os.makedirs(month_dir, exist_ok=True)
    daily_history_file = os.path.join(month_dir, f"{date_str}.jsonl")

    conn.execute("BEGIN TRANSACTION")

    headers = {"User-Agent": "CodeASTSkeletonWire/1.0"}

    for name, url in TARGET_SOURCES.items():
        try:
            r = requests.get(url, headers=headers, timeout=20)
            if r.status_code != 200:
                continue
            raw_code = r.text
        except Exception:
            continue

        orig_bytes = len(raw_code.encode("utf-8"))
        skeleton_code = extract_skeleton(raw_code)
        if not skeleton_code:
            continue

        skel_bytes = len(skeleton_code.encode("utf-8"))
        reduction_pct = ((orig_bytes - skel_bytes) / orig_bytes) * 100.0 if orig_bytes > 0 else 0.0
        content_hash = compute_hash(skeleton_code)

        existing = conn.execute(f"SELECT content_hash FROM package_skeletons WHERE package_name = '{name}'").fetchone()

        escaped_skel = skeleton_code.replace("'", "''")

        if not existing:
            conn.execute(f"""
                INSERT INTO package_skeletons (
                    package_name, source_url, original_size_bytes, skeleton_size_bytes,
                    token_reduction_pct, skeleton_code, content_hash, last_updated_utc
                ) VALUES (
                    '{name}', '{url}', {orig_bytes}, {skel_bytes},
                    {reduction_pct}, '{escaped_skel}', '{content_hash}', '{now_iso}'
                )
            """)

            commit_id = conn.execute("SELECT nextval('seq_commit_id')").fetchone()[0]
            conn.execute(f"""
                INSERT INTO ledger (commit_id, timestamp_utc, operation, package_name, reduction_pct, detail)
                VALUES ({commit_id}, '{now_iso}', 'INIT_SKELETON', '{name}', {reduction_pct}, 'Initial AST skeleton extracted')
            """)

            ledger_entry = {
                "commit_id": commit_id,
                "timestamp_utc": now_iso,
                "operation": "INIT_SKELETON",
                "package_name": name,
                "original_bytes": orig_bytes,
                "skeleton_bytes": skel_bytes,
                "reduction_pct": reduction_pct,
                "content_hash": content_hash
            }
            with open(daily_history_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(ledger_entry) + "\n")

        elif existing[0] != content_hash:
            conn.execute(f"""
                UPDATE package_skeletons SET
                    original_size_bytes = {orig_bytes},
                    skeleton_size_bytes = {skel_bytes},
                    token_reduction_pct = {reduction_pct},
                    skeleton_code = '{escaped_skel}',
                    content_hash = '{content_hash}',
                    last_updated_utc = '{now_iso}'
                WHERE package_name = '{name}'
            """)

            commit_id = conn.execute("SELECT nextval('seq_commit_id')").fetchone()[0]
            conn.execute(f"""
                INSERT INTO ledger (commit_id, timestamp_utc, operation, package_name, reduction_pct, detail)
                VALUES ({commit_id}, '{now_iso}', 'SIGNATURE_DRIFT', '{name}', {reduction_pct}, 'AST interface drift detected')
            """)

            ledger_entry = {
                "commit_id": commit_id,
                "timestamp_utc": now_iso,
                "operation": "SIGNATURE_DRIFT",
                "package_name": name,
                "original_bytes": orig_bytes,
                "skeleton_bytes": skel_bytes,
                "reduction_pct": reduction_pct,
                "content_hash": content_hash
            }
            with open(daily_history_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(ledger_entry) + "\n")

    conn.execute("COMMIT")

    conn.execute(f"COPY (SELECT package_name, source_url, original_size_bytes, skeleton_size_bytes, token_reduction_pct, content_hash, last_updated_utc FROM package_skeletons) TO '{EXPORT_DIR}/skeletons.parquet' (FORMAT PARQUET)")
    build_static_api(conn)
    conn.close()

if __name__ == "__main__":
    run()
