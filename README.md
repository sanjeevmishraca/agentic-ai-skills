# Agentic AI Skills

![Python 3.8+](https://img.shields.io/badge/python-3.8%2B-blue)
![License: MIT](https://img.shields.io/badge/license-MIT-green)
![Claude Code](https://img.shields.io/badge/Claude%20Code-slash%20commands-blueviolet)

A collection of Claude Code skills built on the **WAT framework** (Workflows, Agents, Tools) — an architecture that keeps AI reasoning separate from deterministic code execution for reliable, repeatable results.

---

## Skills

### `/raw-to-jpeg` — RAW Image Processor

Batch-converts RAW camera files to high-quality JPEGs using the **LibRaw engine** (the same core as Adobe Camera Raw / Adobe Bridge). Fully headless — no Adobe software required.

**Features:**
- **Auto-brightness** — per-image histogram analysis targets correct exposure for every shot; no fixed EV setting
- **Smart auto-crop** — detects subjects partially clipped at frame edges (animals, people) and crops them out cleanly
- **Vivid defaults** — Contrast +30, Clarity +25, Vibrance +30, Saturation +15, Sharpness 55
- **Iterative feedback loop** — tell Claude "make it brighter" or "warmer tones" and it re-processes with updated settings
- **Supported formats** — CR2, CR3, NEF, NRW, ARW, RAF, DNG, ORF, RW2, PEF, SRW, 3FR, MEF, MRW, RWL, X3F, ERF

---

## Prerequisites

- **Python 3.8+**
- **[Claude Code](https://claude.ai/code)** — the Anthropic CLI

---

## Setup

```bash
# 1. Clone the repo
git clone https://github.com/sanjeevmishraca/agentic-ai-skills
cd agentic-ai-skills

# 2. Install Python dependencies
pip install -r requirements.txt

# 3. Open the project in Claude Code
claude .
```

---

## Usage

Once the project is open in Claude Code, run:

```
/raw-to-jpeg
```

Claude will ask for the folder containing your RAW files, process them, and save JPEGs to a `Processed/` subfolder next to your originals.

**Example feedback you can give:**
| You say | What changes |
|---------|-------------|
| "Make it brighter" | Increases exposure |
| "Warmer tones" | Raises white balance temperature |
| "More vibrant" | Increases vibrance/saturation |
| "Less noise" | Increases noise reduction |
| "Sharper" | Increases sharpness |
| "More contrast" | Increases contrast |

Claude keeps refining until you're happy, then summarises the final settings so you can replicate them in Lightroom or Bridge.

---

## How It Works

This project follows the **WAT framework**:

| Layer | Role | Files |
|-------|------|-------|
| **Workflow** | Step-by-step SOP | `workflows/raw_to_jpeg.md` |
| **Agent** | Claude Code (you're talking to it) | `.claude/commands/raw-to-jpeg.md` |
| **Tool** | Deterministic Python execution | `tools/raw_to_jpeg.py` |

The AI handles reasoning and user interaction; the Python script handles all pixel manipulation. This separation keeps results consistent and debuggable.

---

## Project Structure

```
.
├── tools/
│   ├── raw_to_jpeg.py        # RAW→JPEG processor (rawpy / LibRaw)
│   └── process_raw.jsx       # Legacy Photoshop ExtendScript (superseded)
├── workflows/
│   └── raw_to_jpeg.md        # Full SOP: inputs, steps, error handling
├── .claude/
│   └── commands/
│       └── raw-to-jpeg.md    # Claude Code slash command definition
├── CLAUDE.md                 # WAT framework agent instructions
├── requirements.txt          # Python dependencies
└── .gitignore
```

---

## Contributing

Issues and PRs welcome. When adding a new skill, follow the WAT pattern:
1. Add the Python tool to `tools/`
2. Add the SOP to `workflows/`
3. Add the slash command to `.claude/commands/`
4. Document it in this README

---

## License

MIT — see [LICENSE](LICENSE)
