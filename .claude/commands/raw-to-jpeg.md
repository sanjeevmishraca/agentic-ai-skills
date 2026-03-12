Follow the workflow defined in `workflows/raw_to_jpeg.md` to process RAW camera images into JPEG files using Adobe Photoshop's Camera Raw engine (the same engine as Adobe Bridge).

## Your responsibilities as the agent:

1. **Collect input** — Ask the user to either:
   - Share the **full folder path** where their RAW images are stored, or
   - **Drop a .zip file** containing the RAW images

2. **Run initial processing** — Once you have the source path, execute:
   ```
   python tools/raw_to_jpeg.py --input "<path>"
   ```
   Output defaults to a `Processed/` subfolder inside the input folder (e.g. `<path>/Processed`). Pass `--output <folder>` to override.

   The tool applies user's preferred style automatically:
   - **Auto-brightness ON**: per-image histogram analysis (P98 highlight protection + P50 midtone target) — no fixed exposure, each image gets the right level
   - **Auto-crop ON**: detects subjects clipped at edges (e.g. partially visible animals) and crops them out using corner-based background estimation
   - Contrast: +30, Clarity: +25 (punch), Vibrance: +30, Saturation: +15 (vivid), Sharpness: 55

3. **Report results** — After processing completes, tell the user:
   - How many images were processed
   - The full path to the output folder (`<input>/Processed/` by default)
   - Any files that failed and why

4. **Gather feedback** — Ask the user if they are satisfied with the results. If not, ask what changes they want. Accept natural language like:
   - "Make it brighter" → increase `exposure`
   - "Warmer tones" → increase `temperature` (set `whiteBalance` to `custom`)
   - "More vibrant" → increase `vibrance`
   - "Less noise" → increase `colorNoiseReduction`
   - "Sharper" → increase `sharpness`
   Refer to the feedback-to-settings mapping table in `workflows/raw_to_jpeg.md`.

5. **Re-process** — Apply changes on top of the previous settings and re-run the tool. The output folder is overwritten each run. Always carry forward all previously applied settings.

6. **Iterate** — Keep refining until the user confirms they are happy with the output.

7. **Final summary** — When done, tell the user:
   - The final path to their processed JPEGs (the output folder used)
   - A summary of the final Camera Raw settings used (so they can replicate in Bridge or Lightroom)

## Important notes:
- Never modify the original RAW files
- Keep a running copy of the current settings dict in your working context across iterations
- If Photoshop is not found, tell the user to install Adobe Photoshop or provide the path via `--photoshop`
- Log files are at `.tmp/raw_processing.log` — read them if anything fails
