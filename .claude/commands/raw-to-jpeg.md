Follow `workflows/raw_to_jpeg.md` (v3.0.0 "final", 2026-11-20 10:22 PST) to turn RAW files into finished, print-ready, signed JPEGs.

## Your responsibilities as the agent

1. **Collect input** — ask for the RAW folder path (or a .zip). Ask where the signature PNGs are if `RTJ_SIGNATURE_DIR` is not set.

2. **First pass** —
   ```
   python tools/raw_to_jpeg.py --input "<path>" --sig-dir "<signature folder>"
   ```
   Pipeline: develop (house look) → expert finish → 3× print upscale → sign. Outputs go to `<path>/Processed/` (`<name>_expert.jpg`, `<name>_expert_print3x.jpg`, and `signed/` copies).

3. **Review every image before handing it over (mandatory)** — look at the full frame and 100 % crops (face/eyes, body, background, print master). Check exposure (bright, never underexposed), composition (animal on a third line, space in the gaze/motion direction), colour (golden coat, no blue cast in shade or markings), and detail (no smearing, blotches, halos, fringes). Fix anything you are not satisfied with *before* reporting.

4. **Fix with a plan file** — write `plan.json` with per-image `exposure`, `crop`, `subject`, `face` (see the workflow) and re-run with `--plan plan.json`.

5. **Report** — files processed, output folder, print size of each master (px and inches at 300 ppi), failures. The final print file is the one in `Processed/signed/`.

6. **Iterate on feedback** using the feedback table in the workflow; carry forward all previous settings.

## Rules
- Never modify the original RAW files.
- Keep intermediates lossless (the tool does this in `.tmp/`).
- Print masters larger than 8000 px may need to be delivered in a zip.
- Logs: `.tmp/raw_processing.log`; results: `.tmp/raw_processing_results.json`.
