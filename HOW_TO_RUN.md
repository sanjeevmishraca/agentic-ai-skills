# How to Run raw-to-jpeg v3

raw-to-jpeg 3.0.0 "final" · guide updated 2026-11-20

Turns a folder of RAW photos into finished, print-ready JPEGs with one command. Originals are never changed.

## Prerequisites (once per computer)

1. **Python 3.12** — Windows: `winget install Python.Python.3.12` · Mac: installer from [python.org/downloads](https://www.python.org/downloads/). Reopen your terminal afterwards.
2. **The code** — on this repo's GitHub page click **Code → Download ZIP** and unzip it, e.g. to `C:\raw-to-jpeg`.
3. **The packages** — in that folder run:

   ```
   cd C:\raw-to-jpeg
   python -m pip install -r requirements.txt
   ```

## Process your RAW files

```
cd C:\raw-to-jpeg
python tools/raw_to_jpeg.py --input "D:\Photos\Kenya2026"
```

Replace the path with your folder of RAW files. Results land in `D:\Photos\Kenya2026\Processed\`:

- `<name>_expert.jpg` — the finished image
- `<name>_expert_print3x.jpg` — 3× print master for large prints
- `signed\` — signed copies, if you set up a signature ([Appendix A](#appendix-a--add-your-signature))

On Mac use `python3` and a path like `~/Pictures/Kenya2026`.

---

# Appendix

## Appendix A — Add your signature

1. Make two transparent PNGs of your signature, one black and one white.
2. Name them exactly `SM_signature_black.png` and `SM_signature_white.png`.
3. Put them in a `signature` folder inside the code folder (e.g. `C:\raw-to-jpeg\signature`), or point to another folder with `--sig-dir "<folder>"`.

The tool picks black or white to suit each corner: 5.25% of the long edge wide, 1% inset, 85% opacity. The `signature` folder is ignored by Git, so it is never uploaded.

## Appendix B — Command options

Add these to the end of the command.

| Option | What it does |
| --- | --- |
| `--output "<folder>"` | Save results somewhere other than `Processed` |
| `--exposure 1.0` | Exposure in stops for every image (default: automatic) |
| `--factor 2` | 2× print master instead of 3×; faster, less memory |
| `--no-upscale` | Skip the print master |
| `--no-finish` | Skip subject-aware finishing (develop only) |
| `--no-sign` | Skip signing |
| `--sig-dir "<folder>"` | Where your signature PNGs are |
| `--plan plan.json` | Per-image settings ([Appendix C](#appendix-c--fine-tune-single-images-with-planjson)) |

Every RAW in the folder and its subfolders is processed; running again overwrites earlier results.

## Appendix C — Fine-tune single images with plan.json

A plan file gives chosen images their own settings; the rest stay automatic. Positions are fractions (0–1) from the top-left corner.

1. Create `plan.json`, keyed by file name without the extension:

   ```json
   {
     "_U4A0059": {
       "exposure": 1.25,
       "crop":    [0.2282, 0.3888, 0.6822, 0.5382],
       "subject": [0.11, 0.11, 0.34, 0.84],
       "face":    [0.3863, 0.2253]
     }
   }
   ```

2. Run with `--plan plan.json` added to the command.

| Setting | Format | Measured on | Use it when |
| --- | --- | --- | --- |
| `exposure` | stops, e.g. `1.25` | — | Too dark or bright (+0.25 to +0.75 is typical) |
| `crop` | `[x, y, w, h]` | Full original frame | Put the animal on a third line, space where it looks |
| `subject` | `[x, y, w, h]` | Cropped image | Finishing brightened the wrong thing |
| `face` | `[x, y]` | Cropped image | Add face clarity and an eye lift |

Example: face at 2400 px in a 6000 px wide image → x = 0.4.

## Appendix D — Let Claude Code run it

1. In the code folder run `claude .` ([Claude Code](https://claude.ai/code)).
2. Type `/raw-to-jpeg` and give it your RAW folder (and signature folder).
3. Claude processes, reviews each image at full size and 100%, and fixes exposure, crop or finishing before reporting.
4. Ask for changes in plain words ("brighter", "more space in front of the animal"); Claude updates the plan and re-runs.

## Appendix E — Review checklist

Before using an image, look at the full frame, then 100% on the eyes and background: exposure bright but not clipped, animal on a third line with space ahead, golden coat with no blue cast, no smearing, halos or colour fringes.

## Appendix F — Troubleshooting

| Problem | Fix |
| --- | --- |
| `'python' is not recognized` | Reinstall Python with "Add python.exe to PATH" ticked, or use `py` instead of `python` |
| `No module named rawpy` (or cv2, numpy, PIL) | Run `python -m pip install -r requirements.txt` in the code folder |
| `No RAW files found` | Check the `--input` path; quote paths with spaces |
| `MemoryError` / stalls on the print master | Use `--factor 2` or crop first; 16 GB RAM recommended |
| `signature PNGs not found` | Check file names and folder (Appendix A) |
| Too dark / bright | Set `exposure` in `plan.json` (Appendix C) |
| Background brightened instead of the animal | Set a tight `subject` box in `plan.json` |
| One file fails | It's skipped and listed at the end; see `.tmp\raw_processing.log` |

How each stage works: [workflows/raw_to_jpeg.md](workflows/raw_to_jpeg.md).
