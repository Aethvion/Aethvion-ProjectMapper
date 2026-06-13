# What is an MCP tool?

## The short version

MCP (Model Context Protocol) is an open standard that lets AI assistants call external tools in a controlled, predictable way. Think of it like a plugin system: you install a tool, the AI gets access to a specific set of actions it can call, and nothing more.

Project Mapper provides 10 of these actions. The AI can call them — it cannot do anything else with your computer through Project Mapper.

---

## Why MCP exists

AI assistants are good at reasoning, writing, and generating code, but they are not connected to your local environment by default. MCP bridges that gap in a structured way:

- The **developer** (you) decides which tools are available and installs them
- The **AI** can call those tools when it decides they are useful
- The **tool** runs on your machine and returns results back to the AI

This is different from giving an AI "access to your computer." The AI can only do what the specific tools allow — nothing more.

---

## How the connection works

When you configure an MCP server in your AI agent's settings, this is what happens at startup:

1. Your AI agent (Claude Code, Cursor, etc.) launches the MCP server as a background process on your machine
2. The server announces which tools it offers (a list with names and descriptions)
3. The AI reads that list and knows it can call those tools during your session
4. When the AI decides to use a tool, it sends a request to the local process — no internet involved
5. The tool runs, returns a result, and the AI continues

The whole exchange is local. The MCP server for Project Mapper is just a Python script running on your machine.

---

## What Project Mapper's MCP tools can do

Project Mapper exposes 10 tools:

| Tool | What the AI can do |
|---|---|
| `pm_scan` | Scan a project directory and build the knowledge graph |
| `pm_context` | Ask "what's relevant to this task?" and get a list of entities |
| `pm_impact` | Ask "what breaks if I change X?" and get affected entities |
| `pm_path` | Find the connection between two parts of the codebase |
| `pm_find` | Look up a specific symbol by name |
| `pm_orphans` | Find dead code — entities with no inbound references |
| `pm_security` | Run a security scan (132+ OWASP patterns) across the full codebase |
| `pm_contribute` | Write a note about something the AI discovered (e.g. "I added rate limiting here") |
| `pm_stats` | Get a summary of what is currently indexed |
| `pm_delta` | See what files changed since the last scan |

That is the complete list. The AI cannot use Project Mapper to read arbitrary files, run commands, access the internet, or do anything outside these 10 actions. For a full description of each tool, see the [PM Tools Reference](pm-tools-reference.md).

---

## Is MCP specific to Project Mapper?

No. MCP is an open standard created by Anthropic and adopted by most major AI coding tools (Claude Code, Cursor, Codex, Antigravity, and others). Many tools use it — file system browsers, database clients, web search, Git integrations, and more.

Project Mapper is one MCP server. You can run multiple MCP servers at the same time, each offering its own set of tools.

---

## Do I need to understand MCP to use Project Mapper?

No. From a user perspective it works like any other tool: you configure it once, restart your AI agent, and then you can ask your AI to use Project Mapper. The protocol is invisible in normal use.

The setup guides in [`docs/howto/`](../howto/) walk through the configuration for each supported agent.
