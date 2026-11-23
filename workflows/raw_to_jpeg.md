# Workflow: RAW → Finished, Print-Ready JPEG

**Version 3.2.0 — 2026-11-20 13:40 PST** (3.0.0 "final" + Best Images / Processed layout; see `CHANGELOG.md`)

## Objective
Turn wildlife RAW files (Canon CR3/CR2 and other LibRaw formats) into finished images in the
photographer's own house look, finished like a fine-art wildlife print, upscaled to the largest
useful print size, and signed. Review every image before handing it over.

---

## Folder layout

```
<shoot folder>/              originals (never modified)
<shoot folder>/Best Images/  stage 0: story-first best shots (RAW + camera JPG) + best_shots_log.csv
<shoot folder>/Processed/    finished JPEGs of everything in Best Images, signed copies in Processed/signed/
```

## Required Inputs

| Input | Description | Required |
|-------|-------------|----------|
| `source` | Folder of RAW files, a single RAW, or a `.zip` | Yes |
| `plan` | Per-image JSON (exposure, crop, subject box, face point) | No – automatic if omitted |
| signature | `SM_signature_black.png` / `SM_signature_white.png` folder (`--sig-dir` or `RTJ_SIGNATURE_DIR`) | No – signing skipped if absent |

---

## Tools Used (pipeline order)

| Stage | Tool | What it does |
|-------|------|--------------|
| orchestrator | `tools/raw_to_jpeg.py` | Runs stage 0, then stages 1–4 per RAW in Best Images, writes logs/results |
| 0 Pick | `tools/best_shots.py` | Best frame per moment + story-first visual review → `Best Images` |
| 1 Develop | `tools/photo_develop.py` + `tools/calib.json` | House look (ACR emulation), auto exposure, optional crop |
| 2 Finish | `tools/expert_finish.py` | Subject mask + local expert edits |
| 3 Upscale | `tools/upscale_print.py` | 3× print master with defringe + masked luminance sharpening |
| 4 Sign | `tools/sign_image.py` | Signature bottom-right on copies in `signed/` |

All intermediates are lossless PNG (in `.tmp/`); only final outputs are JPEG.

---

## Steps

### Step 1 – Collect input
Ask for the RAW folder path (or a zip). Confirm it exists and contains RAW files.

### Step 2 – Pick the best shots (story first)
```bash
python tools/best_shots.py --input "<shoot folder>"
```
Groups frames into sightings (>3 min gap ends one) and **moments** (≤20 s apart and still looking
alike), takes the technically best frame of each moment (focus compared only within the burst),
and writes numbered contact sheets to `.tmp/best_shots/sheet_NN.jpg`.

**Look at every sheet and choose by STORY first:**
- mother & young (e.g. rhino cow with calf walking or running together)
- animals doing something: climbing, drinking, feeding, hunting, interacting
- groups and herds (rhinos resting together, eland with young)
- animals in motion
- one or more animals looking straight at the camera (waterbuck, dik-diks on the track)
- rare animals (black / melanistic leopard)
- dramatic light: side or rim light at golden hour, even when a blue sky makes the frame look cool
Drop: no animal (tents, empty scenes), animal hidden or cut off, weaker near-duplicates of a kept moment.

**Then judge every pick as a WALL PRINT** (matte, glossy, canvas, acrylic or glass) for a wildlife
print business — a record shot is not enough. Reject:
- subject too small / far, buried in vegetation, or face partly hidden, with nothing interesting happening
- no face visible — backs or humps of grazing animals
- the animal looking away when the rest of the frame is good (look for a frame with eye contact or a clear profile)
- a weaker frame of a subject/scene already covered by a stronger pick (no redundancy)
- distractions in frame — vehicle parts, people, bags, tripods: crop them out (`crop` in the plan) or reject
- an animal camouflaged into a busy background — keep only if a tight crop + background blur
  (`tools/separate_subject.py`) makes it separate cleanly
Fix flaws a good frame can lose: grass across the face → `tools/retouch_blade.py`.
Then copy the chosen numbers:
```bash
python tools/best_shots.py --input "<shoot folder>" --keep 3,7,12-15
```
→ `<shoot folder>/Best Images` (RAW + camera JPG) and `best_shots_log.csv`.
(`--auto` copies every moment candidate for unattended runs; the orchestrator uses it when run without `--skip-pick`.)

Why: on the 2026 Laikipia shoot a sharpness-driven, one-per-sighting picker missed all 13 frames the
photographer liked best: whole-frame sharpness called clean-background frames "soft", and one pick per
sighting discarded distinct moments inside long sightings.

### Step 2b – Process everything in Best Images
```bash
python tools/raw_to_jpeg.py --input "<shoot folder>" --skip-pick --sig-dir "<signature folder>"
```
(Without `--skip-pick` the tool runs Step 2 in `--auto` mode first; `--all` processes every RAW, no picking.)
Automatic exposure, automatic subject box (saliency), no crop, no face work → `<shoot folder>/Processed`.

### Step 3 – Review every image yourself before handing over (mandatory)
Open each `<name>_expert.jpg` full frame **and** 100 % crops (face/eyes, body, background).
Check:
- **Exposure** — not underexposed; the photographer prefers bright, airy results.
- **Composition** — animal on a third line with open space in the direction of its gaze/motion; keep 3:2
  unless a panoramic crop serves the image better.
- **Colour** — golden coat, no blue cast in shaded fur or dark markings, calm background.
- **Detail** — no smeared fur, no blotchy or banded background, no halos or colour fringes.
- **Print master** — at 100 %: no halos, fringes, grit or blocking in smooth areas.

### Step 4 – Fix with a plan file and re-run
Write `plan.json` with per-image overrides and re-run with `--plan plan.json`:
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
- `exposure` — EV (auto ≈ camera preview median × 1.12). Raise if it looks dark.
- `crop` — x, y, w, h as fractions of the full 6000×4000 frame (applied before developing).
- `subject` — x, y, w, h box around the animal, fractions of the *cropped* frame (seeds GrabCut).
- `face` — face centre, fractions of the cropped frame (enables face clarity + eye lift).

### Step 5 – Translate feedback

| User says | Change |
|-----------|--------|
| Too dark / underexposed / brighter | `exposure` +0.25 to +0.75 |
| Over-exposed (sunlit rhinos, bright haze) | `exposure` −0.25 to −0.5; auto now never exceeds the camera's own highlight level |
| Too bright | `exposure` −0.25 to −0.5 |
| Move the animal / more space where it looks | `crop`: put the face on a third line, space in gaze direction |
| Crop like my screenshot | template-match the screenshot against the developed frame → `crop` |
| Cut out distraction at an edge | tighten `crop` |
| Face not sharp / eyes dull | set or correct `face` |
| Background too busy / bright | check `subject` box covers only the animal (finish burns/desaturates the rest) |
| Bigger print | `--factor` (3 = default and practical ceiling; 4 only for a specific large print) |

Always carry forward previous settings; only change what was asked.

### Step 6 – Deliver (delivery gate — mandatory, no exceptions)
A delivery is **not done** until `verify_delivery.py check` prints **PASS** against the folder the
photographer actually looks at. (Lesson 2026-11-23: rejected 8533/8603 were still sitting in
`Processed\signed` from an earlier run while the work was reported as done.)

1. **Fresh folder every time.** raw_to_jpeg writes to a new dated folder
   (`Processed/<YYYY-MM-DD> final`, then `… final 2`, …) and refuses a non-empty `--output` (exit 5).
   Never write finals on top of an older run; never use `--allow-existing` for a delivery.
2. **Manifest of exactly what was approved.** After your Step 3 review (and any retouch/sign steps
   done outside the batch), drop rejected images, then:
   `python tools/verify_delivery.py manifest <delivery_dir> --approved <ids> [--allow-extra <user's own files>]`
   It refuses if anything unapproved or any extra folder is present, or an approved image is missing.
   (raw_to_jpeg does this automatically at the end of a clean batch, exit 6 if it fails.)
3. **Copy, then verify the destination itself.** If the folder lives on another machine (device
   bridge), list the destination root and `signed/` with `device_list_dir`, save each listing JSON,
   and run `verify_delivery.py check --manifest … --listing .=root.json --listing signed=signed.json`.
   Locally: `check --manifest … --dir <folder>`. Any EXTRA / MISSING / SIZE / unexpected folder =
   FAIL: move the offenders out (to `_to_delete\`, never delete), re-list, re-check.
4. **If cleanup can't run** (PC locked, file in use, bridge down): do not hand over. Say plainly
   that the folder is not clean yet and what is blocking it.
5. **Handover = the PASS report.** Paste the checker's result and the approved list, then: files
   processed, folder, print size of each master (px and inches at 300 ppi). The print file is the
   one in `signed/`.

---


## Processing philosophy (from the photographer's per-photo reviews — apply to EVERY image)
These are generic rules, not notes about one photo. Check each one before an image is approved.
1. **Eyes tack sharp, always.** Run `tools/eye_sharpen.py` on every image with the eye centres
   (`--eye x,y,r`); check at 200 % that the eyes look natural — no bright specks, magenta
   fringes or grey/teal irises (`--despeck`, `--restore`). A soft eye means find another frame.
2. **Lead room.** Generous space in the direction the animal looks or moves; never park the face
   near the edge it faces.
3. **Never cut the subject.** Full tail, horns, ears, feet. If the camera frame already cuts a key
   part (e.g. a horn out of frame) the image fails — look for a frame of the same moment where it is
   whole. Any other animal cut by the frame edge (half a calf, a face at the edge) must be cropped
   out entirely; if it can't be cropped out without cutting the subject, drop the image.
4. **No dead space.** Trim empty sky/ground; start the crop right at the tail; show more face on
   portraits. Crop foreground down to the meaningful edge (just to the mud, just to the water line).
5. **Background.** Good bokeh sells; more background blur is better (`tools/separate_subject.py`).
   No glow halos around the subject — the finish now feathers its mask inside the edge.
6. **Exposure for print.** Default darker than a screen look: real blacks, mid-tones <= 128,
   highlights rolled off on sunlit rhinos / eland / pale grass (`tools/print_tone.py`, built into
   raw_to_jpeg). Never deliver a white, milky sunlit scene.
7. **Colour.** Warm tones for leopards and golden light (`"warm": 0.04-0.06`); no teal/cyan cast on
   white fur (decool is now part of the finish).
8. **Look for processing damage** on key features (horns, eyes, whiskers) by comparing against the
   camera JPEG at 100 %.
9. **Prefer frames with eyes open and looking at the camera.** If none exists in the sequence, say so.

## Outputs (default `<source>/Processed/<YYYY-MM-DD> final/`)

| File | Spec |
|------|------|
| `<name>_expert.jpg` | finished image — JPEG q97 4:4:4, sRGB, 300 ppi, Artist/Copyright EXIF |
| `<name>_expert_print3x.jpg` | print master, 3× — JPEG q100 4:4:4, sRGB, 300 ppi |
| `signed/<name>_expert*.jpg` | signed copies (signature 5.25 % of long edge, 1 % inset, 85 % opacity, auto black/white) |
| `delivery_manifest.json` | name, size, sha256 of every approved file — the delivery gate checks against this |
| `.tmp/raw_processing.log` | per-file log |
| `.tmp/raw_processing_results.json` | machine-readable summary |

Originals are never modified.

---

## The house look (stage 1) — learned from the photographer's own ACR edit

ACR 18.3.2, PV 15.4, Adobe Color, WB As Shot, Contrast +34, Highlights −87, Shadows +76,
Whites +9, Blacks −34, Texture 0, Clarity +24, Dehaze +23, Vibrance +15, Saturation 0,
linear curve, lens profile + CA, AI Denoise, Sharpen 40 / r1.0 / detail 25,
post-crop vignette −37 (highlight priority). Exposure was +1.15 on the reference; the tool
picks it per image. `calib.json` holds slider gains fitted against the reference export plus a
residual per-channel look LUT. Denoise = light non-local means on detail, Gaussian on smooth
areas, fine dither to prevent banding.

## Expert finish (stage 2)
GrabCut subject mask (feathered) → background: −2…8 % saturation on red/orange earth, 3–11 %
burn with graduated top band, lighter pool around the subject → subject: luminance-ratio dodge
(darks excluded) → local WB warms shaded fur → face clarity 0.22 + fine sharpen 0.15, eye lift
0.20 → dark markings neutralised (blue skylight removed).

## Print upscale (stage 3)
Largest useful size = **3×** (beyond ~3× interpolation only softens). Defringe purple/cyan edges →
Lanczos in 2× steps → unsharp mask r2.0 (scaled with factor) / 90 % / t2 on luminance only,
through a detail mask (smooth areas untouched). Signature is applied after upscaling.

---

## Error handling

| Error | Action |
|-------|--------|
| No RAW files | List supported extensions, ask again |
| Signature PNGs not found | Pipeline continues unsigned; ask for `--sig-dir` |
| GrabCut picks the wrong object | Give a tighter `subject` box in the plan |
| One file fails | Logged; others continue; exit code 4 |
| Very large print master won't transfer as an image | Deliver it inside a zip |

## Notes / lessons
- Review before hand-over is mandatory — a first pass at +0.5 EV was rejected as "very underexposed".
- Lifting shadows amplified a blue cast in dark rosettes; fixed by excluding darks from the lift and
  neutralising markings, not by global WB.
- Lossy JPEG intermediates caused blocking in the 3× master; keep everything PNG until the end.
- Legacy v1 tool (rawpy defaults / Photoshop JSX) is kept in `tools/legacy/` for reference only.
