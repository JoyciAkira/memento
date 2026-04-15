# Memento Claude Code Plugin

Claude Code plugin that exposes Memento as an MCP server and provides convenience slash commands for setup and common operations.

## Prerequisites

- Python 3.10+
- `uv` installed

## Installation (Local)

```bash
claude plugin add /absolute/path/to/memento/.claude-plugin
```

## Available Slash Commands

| Command | Description |
|---------|-------------|
| `/memento:help` | Show available tools and usage |
| `/memento:init` | Set up the MCP server configuration |
| `/memento:search` | Search memories |
| `/memento:mine` | Add a memory (quick capture) |
| `/memento:status` | Show server status |

## Full Documentation

See the repository [README](../README.md) for complete documentation and MCP configuration examples.
