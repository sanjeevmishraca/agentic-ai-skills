# Agentic AI Workspace

This repository follows the WAT framework described in `CLAUDE.md`.

## Installation

```bash
pip install -r requirements.txt
```

## Skills

### `/raw-to-jpeg`
Converts RAW camera files (CR2, CR3, NEF, ARW, RAF, DNG, etc.) to JPEG using the LibRaw engine (same core as Adobe Camera Raw). Features per-image auto-brightness and smart auto-crop for edge-clipped subjects.

**Usage:** Open this project in Claude Code and run `/raw-to-jpeg`

## Structure

- `.tmp/` – temporary files
- `tools/` – deterministic Python scripts
- `workflows/` – markdown SOPs for each workflow
- `.claude/commands/` – Claude Code slash commands
- `CLAUDE.md` – overarching agent instructions
