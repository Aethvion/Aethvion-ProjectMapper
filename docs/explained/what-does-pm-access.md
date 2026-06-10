# What does Project Mapper access on your machine?

This document explains exactly what Project Mapper reads, what it stores, and what it never does — so you can make an informed decision about using it.

---

## What it reads

**During a scan**, Project Mapper reads the source files in the directory you point it at. It reads them the same way a text editor does — as plain text. It does not:

- Execute or compile any code
- Import or load any modules from your project
- Follow symlinks outside the project directory
- Read files outside the directory you specified

The files are read once per scan. After that, Project Mapper works entirely from the stored knowledge graph — your source files are not re-read during queries.

---

## What it stores

Project Mapper saves a knowledge graph to a local folder on your machine:

| OS | Default location |
|---|---|
| Windows | `C:\Users\<YourUsername>\.aethvion_pm\data\` |
| Linux / macOS | `~/.aethvion_pm/data/` |

The knowledge graph contains:

- Names of files, classes, functions, and modules it found
- The relationships between them (imports, calls, extends, etc.)
- Line numbers and file paths
- Docstrings and summary text extracted from the source (if present)

It does **not** store the full source code of your files. The graph is a structured summary, not a copy of your codebase.

You can delete this folder at any time. Project Mapper will rebuild it on the next scan.

---

## What it never does

| Action | Does PM do this? |
|---|---|
| Modify, rename, or delete your source files | **Never** |
| Create files inside your project directory | **Never** |
| Send your code or graph data to any server | **Never** |
| Connect to the internet | **Never** |
| Call any AI or language model during scanning | **Never** |
| Store data in the cloud | **Never** |
| Share anything with Aethvion | **Never** |
| Run or execute code from your project | **Never** |
| Read files outside the scanned directory | **Never** |
| Persist data between machines | **Never** (graph is local only) |

---

## Where does the knowledge graph go when I remove it?

Deleting `~/.aethvion_pm/data/` removes everything Project Mapper has stored. There are no hidden copies, no cloud backups, and no sync. The data exists only on the machine where the scan was run.

---

## Does the AI see my full source code through Project Mapper?

No. When your AI agent calls a Project Mapper tool (like `pm_context` or `pm_impact`), it receives a structured list of relevant entities — names, file paths, relationships, and summaries. It does not receive the raw file contents through Project Mapper.

The AI only reads raw file contents if it separately calls its own file-reading tools (like `Read` in Claude Code). That is a separate action, under your control, not related to Project Mapper.

---

## Does Project Mapper require internet access?

No. The scan, storage, and query tools all run fully offline. The only time network access might be used is if you are running the HTTP API server and accessing it from a different machine — but even then, your code never leaves your local network unless you explicitly expose the server.

---

## Who can see the knowledge graph?

Only processes running on your machine with access to `~/.aethvion_pm/data/`. The data is not encrypted at rest (it is plain JSON), so it has the same access controls as any other file in your home directory. If you are on a shared machine, standard OS file permissions apply.

---

## Summary

Project Mapper scans your code, saves a local summary, and answers questions from your AI agent about structure and relationships. It reads your files during scans, stores a lightweight graph locally, and never communicates with the outside world. Your source code stays on your machine.
