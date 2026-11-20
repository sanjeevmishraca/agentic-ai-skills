# How to Run raw-to-jpeg v3 — Process Your RAW Wildlife Photos

raw-to-jpeg 3.0.0 "final" · guide updated 2026-11-20

## What it does

One command turns a folder of RAW photos into finished, print-ready JPEGs: it develops each RAW in a calibrated wildlife look, adds subject-aware finishing, makes a 3× print master and signs copies. It runs on Windows or Mac and needs no Adobe software.

For every RAW file you get, in a `Processed` folder next to your photos:

| File | What it is | Use it for |
| --- | --- | --- |
| `<name>_expert.jpg` | Finished image, sRGB, 300 ppi | Screen, web, small prints |
| `<name>_expert_print3x.jpg` | Print master, 3× the pixels | Large prints (a 4000 px wide image prints about 40 in wide at 300 ppi) |
| `signed/<same names>` | Copies with your signature bottom-right | The final files to share or print |

Your original RAW files are never changed. Supported formats: CR2, CR3, NEF, NRW, ARW, RAF, DNG, ORF, RW2, PEF, SRW, 3FR, MEF, MRW, RWL, X3F, ERF.

## One-time setup (about 10 minutes)

You need Python 3.12, the code, and four Python packages. Do this once per computer.

1. **Install Python 3.12.**
   - Windows: open Command Prompt and run `winget install Python.Python.3.12`, or download it from [python.org/downloads](https://www.python.org/downloads/) and tick **"Add python.exe to PATH"** on the first install screen.
   - Mac: download it from [python.org/downloads](https://www.python.org/downloads/) and run the installer.
   - Close and reopen Command Prompt / Terminal, then check: `python --version` (Mac: `python3 --version`) should print 3.12.x.
2. **Download the code.** No Git needed.
   - On this repo's GitHub page, click the green **Code** button, then **Download ZIP**.
   - Unzip it to a short path, for example `C:\raw-to-jpeg` (Windows) or `~/raw-to-jpeg` (Mac).
   - If you use Git instead: `git clone https://github.com/sanjeevmishraca/agentic-ai-skills raw-to-jpeg`
3. **Open a terminal in that folder.**
   - Windows: `cd C:\raw-to-jpeg` (adjust if the unzipped folder has another name, such as `agentic-ai-skills-master`).
   - Mac: `cd ~/raw-to-jpeg`
4. **Install the packages:** `python -m pip install -r requirements.txt` (Mac: `python3 -m pip install -r requirements.txt`). This installs rawpy (RAW decoding), Pillow, NumPy and OpenCV.
5. **Check it works:** `python tools/raw_to_jpeg.py --version` should print `raw_to_jpeg 3.0.0 (2026-11-20 10:22 PST)`.

Recommended hardware: 16 GB RAM. A 3× print master of a full 24 MP frame is very large (about 18000 × 12000 px).

## Optional: add your signature

Skip this and the tool still runs; it just doesn't make signed copies.

1. Make two transparent PNGs of your signature: one black, one white. The tool picks whichever shows up better against each image's bottom-right corner.
2. Name them exactly `SM_signature_black.png` and `SM_signature_white.png`.
3. Put both in a folder named `signature` inside the code folder (for example `C:\raw-to-jpeg\signature`). The tool finds them there automatically. To keep them somewhere else, add `--sig-dir "<that folder>"` when you run it.

Defaults: 5.25% of the image's long edge wide, 1% in from the right and bottom, 85% opacity. The `signature` folder is ignored by Git, so your signature is never uploaded.

## Run it

1. Put the RAW files you want processed in one folder, for example `D:\Photos\Kenya2026`. Copy only the files you want, since every RAW in the folder and its subfolders gets processed.
2. Open Command Prompt / Terminal and go to the code folder: `cd C:\raw-to-jpeg`
3. Run:

   ```
   python tools/raw_to_jpeg.py --input "D:\Photos\Kenya2026"
   ```

4. Watch the progress. Each file prints its exposure, "expert finish done", the print size, and the signed files. Expect about 40 seconds to a few minutes per image, depending on your computer.
5. Open `D:\Photos\Kenya2026\Processed\`. The files in `Processed\signed\` are the final ones.
6. **Look at every image before you use it**: the full picture, then zoomed to 100% on the eyes and the background. If one needs changes, fix it with a plan file (next section).

Useful options (add them to the end of the command):

| Option | What it does |
| --- | --- |
| `--output "<folder>"` | Saves results somewhere other than `Processed` |
| `--exposure 1.0` | Sets exposure in stops for every image (default: automatic) |
| `--factor 2` | Smaller print master (2× instead of 3×); faster, uses less memory |
| `--no-upscale` | Skips the print master |
| `--no-finish` | Skips the subject-aware finishing (develop only) |
| `--no-sign` | Skips signing |
| `--sig-dir "<folder>"` | Where your signature PNGs are |
| `--plan plan.json` | Per-image settings (next section) |

Running it again on the same folder overwrites the earlier results.

## Fine-tune an image with plan.json

A plan file gives one image its own exposure, crop, subject box and face point; every other image stays automatic. All positions are fractions from 0 to 1, measured from the top-left corner.

1. Create a text file named `plan.json` (anywhere, for example in the code folder).
2. Add one entry per image you want to adjust, keyed by its file name without the extension:

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

3. Run with the plan: `python tools/raw_to_jpeg.py --input "D:\Photos\Kenya2026" --plan plan.json`

| Setting | Format | Measured on | Change it when |
| --- | --- | --- | --- |
| `exposure` | stops, e.g. `1.25` | — | The image looks too dark or too bright (+0.25 to +0.75 is a typical fix) |
| `crop` | `[x, y, width, height]` | Full original frame | You want the animal on a third line with space in the direction it looks or moves |
| `subject` | `[x, y, width, height]` | Cropped image | Finishing brightened the wrong thing; draw the box tightly around the animal |
| `face` | `[x, y]` | Cropped image | You want extra clarity on the face and a lift in the eyes |

Example: an image 6000 px wide with the face at 2400 px from the left has a face x of 2400 / 6000 = 0.4.

## Or let Claude Code run it for you

With [Claude Code](https://claude.ai/code) installed, Claude runs the tool, reviews each image and writes the plan file for you.

1. Open a terminal in the code folder and start Claude Code: `claude .`
2. Type `/raw-to-jpeg` and give it the folder of RAW files (and your signature folder, if you have one).
3. Claude processes the images, checks each one at full size and at 100%, and fixes exposure, crop or finishing before reporting back.
4. Ask for changes in plain words, such as "brighter", "more space in front of the animal" or "crop like this screenshot". Claude updates the plan and re-runs the tool.

## Troubleshooting

| Problem | Fix |
| --- | --- |
| `'python' is not recognized` | Python isn't on PATH. Reinstall it with "Add python.exe to PATH" ticked, or use `py` instead of `python` on Windows. |
| `No module named rawpy` (or cv2, numpy, PIL) | Run `python -m pip install -r requirements.txt` from the code folder. |
| `No RAW files found` | Check the `--input` path and that the files have a supported extension. Put paths with spaces in quotes. |
| `MemoryError` or the computer stalls on the print master | Use `--factor 2`, or crop the image first in a plan file. Close other apps. |
| `signature PNGs not found ... skipping signing` | Name the files exactly `SM_signature_black.png` / `SM_signature_white.png` and put them in `signature\` or pass `--sig-dir`. |
| Image too dark or too bright | Add `"exposure"` for that image in `plan.json`. |
| The background got brightened instead of the animal | Add a tight `"subject"` box for that image in `plan.json`. |
| A file fails but others work | It's skipped and listed at the end; details are in `.tmp\raw_processing.log` inside the code folder. |

For how each stage works, see [workflows/raw_to_jpeg.md](workflows/raw_to_jpeg.md).
