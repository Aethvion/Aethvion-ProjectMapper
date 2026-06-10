# What is Project Mapper?

## The short version

Project Mapper is a tool that reads your codebase and builds a structured map of it — every file, class, function, and how they connect to each other. Instead of your AI assistant reading entire files every time you ask a question, it queries that map and gets exactly what it needs in milliseconds.

---

## The problem it solves

AI coding assistants (Claude, Cursor, Copilot, etc.) are powerful, but they have a limitation: they can only hold a certain amount of text in memory at once (called the "context window"). When you ask about a complex feature, the AI often has to read 5–20 files just to answer. That is:

- **Slow** — loading that much text takes time
- **Expensive** — you pay per token (word), and reading entire files adds up fast
- **Less accurate** — when the context window fills up, the AI starts "forgetting" what it read earlier

Project Mapper solves this by scanning your code once and storing a summary — who calls what, what extends what, where each function lives. When the AI needs to understand something, it queries the map instead of reading raw files.

---

## How it works, step by step

1. **You trigger a scan** — either by telling your AI agent to scan the project, or by calling the API directly. This is the only step that takes more than a second.

2. **Project Mapper reads your source files** — it uses static analysis (reading code without running it) to find every module, class, function, and relationship. No AI is involved in this step. It is purely pattern-matching on text.

3. **A knowledge graph is saved locally** — the results are stored in a small database on your own machine (by default in `~/.aethvion_pm/data/`). Nothing is sent anywhere.

4. **Your AI agent queries the graph** — instead of reading files, it calls tools like `pm_context` ("what's relevant to this task?") or `pm_impact` ("what breaks if I change this?"). Each query takes 10–100 milliseconds and returns only the relevant entities.

---

## What Project Mapper is not

- **Not an AI** — the scan uses traditional static code analysis (AST parsing), the same technique used by IDEs and linters. No language model is involved in reading your code.
- **Not a cloud service** — everything runs on your machine. The knowledge graph never leaves your computer.
- **Not a code editor or executor** — it never modifies, runs, or compiles your code. It only reads.
- **Not a replacement for your AI** — it is a tool your AI uses. It makes the AI faster and cheaper; it does not replace the reasoning the AI does.

---

## Supported languages

Project Mapper currently extracts structured data from:

| Language | What is extracted |
|---|---|
| Python | Modules, classes, functions, imports, calls, docstrings |
| TypeScript / JavaScript | Classes, interfaces, functions, arrow functions, imports, JSDoc |
| Java / Kotlin | Classes, interfaces, methods, imports |
| C# | Classes, interfaces, methods, namespaces |
| PHP | Classes, functions, methods |
| Ruby | Classes, modules, methods |
| C / C++ | Functions, structs, includes |
| Rust | Functions, structs, traits, modules |
| Swift | Classes, structs, protocols, functions |

Other file types are indexed by file path only (not parsed) so they still appear in the graph.

---

## How much does a scan cost?

Nothing beyond electricity and a few seconds of CPU. The scan is local, uses no API calls, and produces no network traffic. Subsequent scans are incremental — only changed files are re-processed, so a repo you've already scanned typically updates in under 2 seconds.
