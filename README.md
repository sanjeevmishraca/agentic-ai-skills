# Agentic AI Skills

![Python 3.8+](https://img.shields.io/badge/python-3.8%2B-blue)
![License: MIT](https://img.shields.io/badge/license-MIT-green)
![Claude Code](https://img.shields.io/badge/Claude%20Code-slash%20commands-blueviolet)

A collection of Claude Code skills built on the **WAT framework** (Workflows, Agents, Tools) — an architecture that keeps AI reasoning separate from deterministic code execution for reliable, repeatable results.

---

## Skills

### `/raw-to-jpeg` — RAW → finished, print-ready JPEG · **v3.0.0 "final" (2026-11-20 10:22 PST)**

Turns wildlife RAW files into finished, signed, print-ready images in one command. Fully headless (LibRaw via rawpy + OpenCV) — no Adobe software required.

**Pipeline:**
1. **Develop** — a house look learned from the photographer's own Camera Raw edit (Contrast +34, Highlights −87, Shadows +76, Whites +9, Blacks −34, Clarity +24, Dehaze +23, Vibrance +15, vignette −37), calibrated against the real export. Auto exposure is set relative to the camera's own preview. Optional crop.
2. **Expert finish** — subject mask; calmer background, subject dodge, warm shaded fur, crisp face and eyes, clean black markings.
3. **Print upscale** — 3× master (largest useful size), with defringing and detail-masked luminance sharpening, at 300 ppi.
4. **Sign** — signature bottom-right on copies in `signed/`.

**Supported formats** — CR2, CR3, NEF, NRW, ARW, RAF, DNG, ORF, RW2, PEF, SRW, 3FR, MEF, MRW, RWL, X3F, ERF

---

**New here? Follow the step-by-step [How to Run guide](HOW_TO_RUN.md).**

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

Claude will ask for the folder containing your RAW files. It runs the pipeline, **reviews every image (full frame + 100 % crops) before handing it over**, and saves the results to `Processed/` next to your originals:

| File | What it is |
|------|-----------|
| `<name>_expert.jpg` | finished image (sRGB, 300 ppi) |
| `<name>_expert_print3x.jpg` | 3× print master |
| `signed/…` | signed copies — the final files to print |

Direct use:
```bash
python tools/raw_to_jpeg.py --input <folder> --sig-dir <signature-folder> [--plan plan.json]
```
`plan.json` holds per-image `exposure`, `crop`, `subject` and `face` (see `workflows/raw_to_jpeg.md`). Signature PNGs (`SM_signature_black.png` / `SM_signature_white.png`) are kept locally, never committed.

**Example feedback you can give:**
| You say | What changes |
|---------|-------------|
| "Make it brighter" | Raises exposure |
| "Move the animal left / more space where it looks" | Re-crops on a third line |
| "Crop like this screenshot" | Matches the screenshot crop |
| "Eyes aren't sharp" | Sets the face point for clarity and eye lift |
| "Bigger print" | Changes the upscale factor |

Claude keeps refining until you're happy.

---

## How It Works

This project follows the **WAT framework**:

| Layer | Role | Files |
|-------|------|-------|
| **Workflow** | Step-by-step SOP | `workflows/raw_to_jpeg.md` |
| **Agent** | Claude Code (you're talking to it) | `.claude/commands/raw-to-jpeg.md` |
| **Tool** | Deterministic Python execution | `tools/raw_to_jpeg.py` → `photo_develop.py`, `expert_finish.py`, `upscale_print.py`, `sign_image.py` |

The AI handles reasoning and user interaction; the Python script handles all pixel manipulation. This separation keeps results consistent and debuggable.

---

## Project Structure

```
.
├── tools/
│   ├── raw_to_jpeg.py        # v3 pipeline orchestrator
│   ├── photo_develop.py      # stage 1: house-look RAW development
│   ├── calib.json            # calibrated gains + look LUT
│   ├── expert_finish.py      # stage 2: subject-aware finishing
│   ├── upscale_print.py      # stage 3: 3x print master
│   ├── sign_image.py         # stage 4: signature
│   └── legacy/               # v1 rawpy tool + Photoshop JSX (superseded)
├── workflows/
│   └── raw_to_jpeg.md        # Full SOP: inputs, steps, error handling
├── .claude/
│   └── commands/
│       └── raw-to-jpeg.md    # Claude Code slash command definition
├── HOW_TO_RUN.md              # step-by-step guide for anyone
├── CHANGELOG.md              # versions (raw-to-jpeg 3.0.0 final, 2026-11-20)
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
