# Workflow: RAW Image → JPEG Processor

## Objective
Convert RAW camera files (CR2, CR3, NEF, ARW, RAF, DNG, etc.) to high-quality JPEG images using Adobe Photoshop's Camera Raw engine — the same engine powering Adobe Bridge. Iterate on the output with user feedback until they are satisfied.

---

## Required Inputs

| Input | Description | Required |
|-------|-------------|----------|
| `source` | Path to a folder containing RAW files **or** a `.zip` archive | Yes |
| `settings` | Camera Raw adjustment overrides (JSON) | No – defaults applied |

---

## Tools Used

| Tool | Purpose |
|------|---------|
| `tools/raw_to_jpeg.py` | Python orchestrator — validates input, writes job file, launches Photoshop |
| `tools/process_raw.jsx` | ExtendScript executed inside Photoshop — applies Camera Raw settings, exports JPEG |

---

## Steps

### Step 1 – Collect Input

Ask the user:

> "Please share the **folder path** where your RAW images are stored, or **drop a .zip file** containing them."

- If they give a folder path: verify it exists with `os.path.exists()`
- If they drop/share a zip: use the zip path as `--input`
- Extract and scan for RAW files. If none found, tell the user which extensions are supported and ask again.

---

### Step 2 – Run Initial Processing (Default Settings)

Run with default Camera Raw settings first:

```bash
python tools/raw_to_jpeg.py --input "<source_path>"
```

Output defaults to `<source_path>/Processed`. Pass `--output <folder>` to override.

Default settings applied (user's preferred style):
- JPEG Quality: 10/12, sRGB, 300 DPI
- White Balance: As Shot
- **auto_brightness: True** — half-size probe render analysed per image; EV computed to protect highlights (P98=225) and hit natural midtones (P50=115); user's `exposure` offset added on top
- **auto_crop: True** — corner-based background model detects subjects clipped at any edge, crops to first clear gap
- Contrast: +30, Clarity: +25 (punch)
- Saturation: +15, Vibrance: +30 (vivid colours)
- Sharpness: 55

The tool will:
1. For each RAW file: render half-size probe → compute auto EV → render full-size → apply tone/colour → auto-crop → save JPEG
2. Results written to `.tmp/raw_processing_results.json`

---

### Step 3 – Share Results with User

After processing completes:

1. List all processed JPEG filenames from `results["processed"]`
2. Tell the user: "Your images have been processed and saved to `<source_path>/Processed/`"
3. Provide the full path to the output folder
4. If any files failed, show which ones and the error message

---

### Step 4 – Gather Feedback

Ask the user:

> "Are you happy with the results? If you'd like adjustments, tell me what you'd like changed.
>
> For example:
> - *'Make it brighter'* → I'll increase exposure
> - *'Warmer tones'* → I'll raise the white balance temperature
> - *'More vibrant colours'* → I'll increase vibrance/saturation
> - *'Less noise'* → I'll increase noise reduction
> - *'Sharper'* → I'll increase sharpness"

---

### Step 5 – Translate Feedback → Settings

Map natural language feedback to Camera Raw parameters:

| User Says | Parameter | Adjustment |
|-----------|-----------|------------|
| Brighter / too dark | `exposure` | +0.5 to +1.5 |
| Darker / too bright | `exposure` | -0.5 to -1.5 |
| More contrast | `contrast` | +20 to +40 |
| Recover highlights | `highlights` | -30 to -60 |
| Lift shadows | `shadows` | +20 to +40 |
| Warmer | `temperature` + `whiteBalance: custom` | +500 to +1500 K |
| Cooler | `temperature` + `whiteBalance: custom` | -500 to -1500 K |
| More vibrant / pop | `vibrance` | +20 to +40 |
| More saturated | `saturation` | +15 to +30 |
| Less saturated / muted | `saturation` | -15 to -30 |
| Sharper | `sharpness` | +20 to +40 (cap at 100) |
| Cleaner / less noise | `colorNoiseReduction` | +20 to +30, `luminanceSmoothing` +10 |
| More clarity / detail | `clarity` | +15 to +30 |
| Soft / dreamy | `clarity` | -10 to -20 |
| Fix white balance | `whiteBalance` | set to "auto" or "daylight" etc. |

**Always carry forward all previous settings** when re-running. Only change the parameters the user requested.

---

### Step 6 – Re-Process with Updated Settings

Build the updated settings JSON and re-run:

```bash
python tools/raw_to_jpeg.py \
  --input "<source_path>" \
  --settings '{"exposure": 0.7, "vibrance": 25, "sharpness": 40}'
```

The new JPEGs overwrite the previous ones in `<source_path>/Processed/` (same filenames, updated content).

---

### Step 7 – Iterate Until Satisfied

Repeat Steps 3–6 until the user confirms they are happy. Then:

1. Confirm final output location: `<source_path>/Processed/`
2. Offer to copy/move files to a permanent destination if desired
3. Summarise the final Camera Raw settings used (so user can replicate in Bridge/Lightroom)

---

## Camera Raw Settings Reference

```json
{
  "jpegQuality":          10,
  "colorSpace":           "sRGB",
  "resolution":           300,
  "size":                 "large",
  "whiteBalance":         "asShot",
  "temperature":          null,
  "tint":                 null,
  "exposure":             0.0,
  "contrast":             0,
  "highlights":           0,
  "shadows":              5,
  "whites":               0,
  "blacks":               0,
  "clarity":              0,
  "saturation":           0,
  "vibrance":             0,
  "sharpness":            25,
  "luminanceSmoothing":   0,
  "colorNoiseReduction":  25
}
```

---

## Error Handling

| Error | Action |
|-------|--------|
| Photoshop not found | Tell user to install Photoshop or pass `--photoshop <path>` |
| No RAW files found | List supported extensions; ask user to confirm folder |
| Zip extraction fails | Check zip integrity; ask user to re-upload |
| Individual file fails | Log it, continue processing remaining files; report at end |
| Photoshop dialog appears | Ensure `app.displayDialogs = DialogModes.NO` is set in JSX |
| Timeout | Increase `--timeout` (default 300s). Large files take longer. |

---

## Output

- **Location:** `<input_folder>/Processed/<filename>.jpg`
- **Format:** JPEG, JPEG quality 10/12 (adjustable), sRGB, 8-bit
- **Naming:** Same as source RAW file, extension changed to `.jpg`
- **Metadata:** Colour profile embedded

---

## Notes

- Adobe Photoshop's Camera Raw is **the same engine** used by Adobe Bridge. Results are identical to processing via Bridge's Output workspace.
- Settings are **non-destructive** to originals — RAW files are never modified.
- Each iteration **overwrites** `<input_folder>/Processed/` with updated JPEGs.
- `.tmp/raw_processing.log` contains per-file processing logs for debugging.
- `.tmp/raw_processing_results.json` contains the machine-readable summary of the last run.
