"""
Security Benchmark: Agent without PM vs Agent with PM + pm_security
Target: OWASP Juice Shop
Rules:  SOLUTIONS.md must NOT be read by either agent.

Metrics collected per run:
  - Wall-clock time (seconds)
  - Input tokens / output tokens / total tokens
  - Number of unique vulnerabilities reported (file:line or description)
  - Number of tool calls made
"""

from __future__ import annotations

import json
import os
import sys
import time
import threading
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# env + path setup
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).parent))
from dotenv import load_dotenv
load_dotenv("C:/Aethvion/Aethvion-Suite/.env")

GOOGLE_API_KEY = os.getenv("GOOGLE_AI_API_KEY", "")
if not GOOGLE_API_KEY:
    sys.exit("GOOGLE_AI_API_KEY not found")

JUICE_SHOP = str(Path("C:/Aethvion/Aethvion-ProjectMapper-Security/juice-shop-master"))
MODEL      = "gemini-2.5-flash"

TASK = (
    "You are a security engineer performing a code review of an OWASP Juice Shop "
    "application. Your goal is to find as many real security vulnerabilities as possible. "
    "For each finding, report: the file path, line number (if determinable), vulnerability "
    "type (e.g. SQL Injection, XSS, RCE), and a one-line description of why it is dangerous. "
    "Do NOT read or reference SOLUTIONS.md. "
    "When you are done, output a final section titled '=== FINDINGS ===' "
    "followed by a numbered list of all vulnerabilities you found."
)

# ---------------------------------------------------------------------------
# Gemini SDK helpers
# ---------------------------------------------------------------------------
from google import genai
from google.genai import types

client = genai.Client(api_key=GOOGLE_API_KEY)

# ---------------------------------------------------------------------------
# File-system tools available to the NO-PM agent
# ---------------------------------------------------------------------------

def _read_file(path: str) -> str:
    """Read a file from the Juice Shop source tree."""
    full = Path(JUICE_SHOP) / path
    if not full.resolve().is_relative_to(Path(JUICE_SHOP).resolve()):
        return "Error: path traversal not allowed"
    if "SOLUTIONS" in path.upper():
        return "Error: reading SOLUTIONS.md is not allowed"
    if not full.exists():
        return f"Error: {path} does not exist"
    try:
        return full.read_text(encoding="utf-8", errors="replace")[:8000]
    except Exception as e:
        return f"Error reading file: {e}"

def _list_dir(path: str = "") -> str:
    """List files/dirs in the Juice Shop tree."""
    full = Path(JUICE_SHOP) / path if path else Path(JUICE_SHOP)
    if not full.resolve().is_relative_to(Path(JUICE_SHOP).resolve()):
        return "Error: path traversal not allowed"
    if not full.exists():
        return f"Error: {path} does not exist"
    entries = []
    for p in sorted(full.iterdir()):
        tag = "DIR" if p.is_dir() else "FILE"
        entries.append(f"[{tag}] {p.relative_to(Path(JUICE_SHOP))}")
    return "\n".join(entries[:200])

def _grep(pattern: str, path: str = "") -> str:
    """Search for a regex pattern in the Juice Shop source."""
    import re
    base = Path(JUICE_SHOP) / path if path else Path(JUICE_SHOP)
    if "SOLUTIONS" in str(path).upper():
        return "Error: searching SOLUTIONS.md is not allowed"
    results: list[str] = []
    try:
        rx = re.compile(pattern, re.IGNORECASE)
    except re.error as e:
        return f"Regex error: {e}"
    for f in base.rglob("*"):
        if not f.is_file():
            continue
        if f.suffix not in {".ts", ".js", ".json", ".html", ".md", ".txt", ".yaml", ".yml"}:
            continue
        if "SOLUTIONS" in f.name.upper():
            continue
        try:
            for i, line in enumerate(f.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                if rx.search(line):
                    rel = f.relative_to(Path(JUICE_SHOP))
                    results.append(f"{rel}:{i}: {line.rstrip()}")
                    if len(results) >= 50:
                        break
        except Exception:
            pass
        if len(results) >= 50:
            break
    return "\n".join(results) if results else "No matches found"

NO_PM_TOOLS = [
    types.Tool(function_declarations=[
        types.FunctionDeclaration(
            name="read_file",
            description="Read a source file from the Juice Shop project. Returns up to 8000 chars.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "path": types.Schema(type=types.Type.STRING, description="Relative path from Juice Shop root, e.g. 'routes/login.ts'"),
                },
                required=["path"],
            ),
        ),
        types.FunctionDeclaration(
            name="list_dir",
            description="List contents of a directory in the Juice Shop project.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "path": types.Schema(type=types.Type.STRING, description="Relative path (empty string for root)"),
                },
            ),
        ),
        types.FunctionDeclaration(
            name="grep",
            description="Search for a regex pattern across Juice Shop source files (.ts .js .html etc).",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "pattern": types.Schema(type=types.Type.STRING, description="Regex pattern to search for"),
                    "path":    types.Schema(type=types.Type.STRING, description="Sub-directory to search in (empty = all)"),
                },
                required=["pattern"],
            ),
        ),
    ])
]

# ---------------------------------------------------------------------------
# PM tools available to the PM agent
# ---------------------------------------------------------------------------

from project_mapper.mcp_tools import (
    handle_pm_security, handle_pm_security_triage,
    handle_pm_context, handle_pm_find,
    MCPContext, HANDLERS,
)

_PM_CTX = MCPContext(
    db_root=Path("C:/Users/Gebruiker/.aethvion_pm/data/juice_shop"),
    db_name="juice_shop",
    writer=None, index=None, file_manifest=None,
    project_root=JUICE_SHOP,
    scan_lock=threading.Lock(),
)

def _call_pm(name: str, args: dict) -> str:
    args.setdefault("project_root", JUICE_SHOP)
    handler = HANDLERS.get(name)
    if not handler:
        return f"Unknown PM tool: {name}"
    try:
        return handler(args, _PM_CTX)
    except Exception as e:
        return f"PM tool error: {e}"

PM_TOOLS = [
    types.Tool(function_declarations=[
        types.FunctionDeclaration(
            name="pm_security",
            description=(
                "Run the OWASP SAST security scanner on the project. "
                "Returns a structured report of findings grouped by OWASP category. "
                "Args: severity (comma-separated: critical,high,medium,low), max_results (int)."
            ),
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "severity":    types.Schema(type=types.Type.STRING, description="e.g. 'critical,high,medium,low'"),
                    "max_results": types.Schema(type=types.Type.INTEGER),
                },
            ),
        ),
        types.FunctionDeclaration(
            name="pm_context",
            description="Get context about the project structure and key entities.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "query": types.Schema(type=types.Type.STRING),
                    "slim":  types.Schema(type=types.Type.BOOLEAN),
                },
                required=["query"],
            ),
        ),
        types.FunctionDeclaration(
            name="pm_find",
            description="Find a specific symbol/function and its callers/callees.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "name": types.Schema(type=types.Type.STRING),
                },
                required=["name"],
            ),
        ),
        types.FunctionDeclaration(
            name="read_file",
            description="Read a source file from the Juice Shop project (for deeper inspection).",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "path": types.Schema(type=types.Type.STRING),
                },
                required=["path"],
            ),
        ),
    ])
]

# ---------------------------------------------------------------------------
# Agentic loop
# ---------------------------------------------------------------------------

def run_agent(label: str, tools, tool_dispatcher: dict[str, Any]) -> dict:
    """Run one agentic session and return stats + findings."""
    print(f"\n{'='*60}")
    print(f"  RUNNING: {label}")
    print(f"{'='*60}\n")

    messages: list[types.Content] = [
        types.Content(role="user", parts=[types.Part(text=TASK)])
    ]

    total_input_tokens  = 0
    total_output_tokens = 0
    tool_calls          = 0
    final_text          = ""
    t_start             = time.perf_counter()

    while True:
        resp = client.models.generate_content(
            model=MODEL,
            contents=messages,
            config=types.GenerateContentConfig(
                tools=tools,
                temperature=0.2,
                max_output_tokens=8192,
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
        )

        # Accumulate token counts
        if resp.usage_metadata:
            total_input_tokens  += resp.usage_metadata.prompt_token_count or 0
            total_output_tokens += resp.usage_metadata.candidates_token_count or 0

        candidate = resp.candidates[0]
        model_content = candidate.content
        messages.append(model_content)

        # Collect any text parts
        for part in model_content.parts:
            if part.text:
                final_text += part.text

        # Check for function calls
        fn_calls = [p for p in model_content.parts if p.function_call]
        if not fn_calls:
            break  # model is done

        # Execute all function calls and feed results back
        tool_results = []
        for fc in fn_calls:
            tool_calls += 1
            fn_name = fc.function_call.name
            fn_args = dict(fc.function_call.args) if fc.function_call.args else {}

            print(f"  [{label}] tool_call #{tool_calls}: {fn_name}({json.dumps({k: v for k,v in fn_args.items() if k != 'project_root'})[:80]})")

            fn_impl = tool_dispatcher.get(fn_name)
            if fn_impl:
                result = fn_impl(**fn_args)
            else:
                result = f"Unknown tool: {fn_name}"

            # Truncate extremely long results to avoid context explosion
            if len(result) > 12000:
                result = result[:12000] + "\n...[truncated]"

            tool_results.append(
                types.Part(
                    function_response=types.FunctionResponse(
                        name=fn_name,
                        response={"result": result},
                    )
                )
            )

        messages.append(types.Content(role="user", parts=tool_results))

    elapsed = time.perf_counter() - t_start

    # Extract findings from final text
    findings_raw = []
    if "=== FINDINGS ===" in final_text:
        section = final_text.split("=== FINDINGS ===", 1)[1]
        for line in section.splitlines():
            line = line.strip()
            if line and (line[0].isdigit() or line.startswith("-")):
                findings_raw.append(line)

    return {
        "label":          label,
        "time_s":         round(elapsed, 1),
        "input_tokens":   total_input_tokens,
        "output_tokens":  total_output_tokens,
        "total_tokens":   total_input_tokens + total_output_tokens,
        "tool_calls":     tool_calls,
        "findings_count": len(findings_raw),
        "findings":       findings_raw,
        "final_text":     final_text,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # No-PM dispatcher
    no_pm_dispatch = {
        "read_file": lambda path="": _read_file(path),
        "list_dir":  lambda path="": _list_dir(path),
        "grep":      lambda pattern="", path="": _grep(pattern, path),
    }

    # PM dispatcher
    pm_dispatch = {
        "pm_security": lambda **kw: _call_pm("pm_security", kw),
        "pm_context":  lambda **kw: _call_pm("pm_context", kw),
        "pm_find":     lambda **kw: _call_pm("pm_find", kw),
        "read_file":   lambda path="": _read_file(path),
    }

    results = []

    r1 = run_agent("No PM  (file tools only)", NO_PM_TOOLS, no_pm_dispatch)
    results.append(r1)

    r2 = run_agent("PM + pm_security", PM_TOOLS, pm_dispatch)
    results.append(r2)

    # ---------------------------------------------------------------------------
    # Print comparison table
    # ---------------------------------------------------------------------------
    print("\n\n" + "="*60)
    print("  SECURITY BENCHMARK RESULTS")
    print("="*60)

    headers = ["Metric", "No PM", "PM + pm_security"]
    rows = [
        ["Time (s)",        f"{r1['time_s']}s",         f"{r2['time_s']}s"],
        ["Input tokens",    f"{r1['input_tokens']:,}",   f"{r2['input_tokens']:,}"],
        ["Output tokens",   f"{r1['output_tokens']:,}",  f"{r2['output_tokens']:,}"],
        ["Total tokens",    f"{r1['total_tokens']:,}",   f"{r2['total_tokens']:,}"],
        ["Tool calls",      str(r1['tool_calls']),       str(r2['tool_calls'])],
        ["Vulns found",     str(r1['findings_count']),   str(r2['findings_count'])],
    ]

    col_w = [20, 22, 22]
    def row_str(cells):
        return "  " + "".join(c.ljust(w) for c, w in zip(cells, col_w))

    print(row_str(headers))
    print("  " + "-" * sum(col_w))
    for r in rows:
        print(row_str(r))

    print("\n--- No PM findings ---")
    for f in r1["findings"]:
        print(f"  {f}")

    print("\n--- PM + pm_security findings ---")
    for f in r2["findings"]:
        print(f"  {f}")

    # Save full output
    out_path = Path(__file__).parent / "security_benchmark_result.json"
    out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nFull results saved to: {out_path}")
