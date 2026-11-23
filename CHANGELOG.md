# Changelog

## raw-to-jpeg 3.4.0 — 2026-11-23 (delivery gate)

### Fixed
- Stale files from earlier runs could sit next to the new finals (Laikipia: rejected 8533/8603 were
  still in `Processed\signed` when the work was reported as done). Every run now writes to a NEW
  dated folder `Processed/<date> final`, and a non-empty `--output` is refused (exit 5) unless
  `--allow-existing`.

### Added
- tools/verify_delivery.py — `manifest` records exactly the approved files (name, size, sha256) and
  refuses a folder holding anything unapproved; `check` compares a local folder or remote listings
  (device bridge) with the manifest and prints PASS/FAIL with every EXTRA / MISSING / SIZE problem
  (exit 3 on FAIL).
- raw_to_jpeg runs manifest + check at the end of every clean batch (exit 6 if verification fails).
- Workflow Step 6 is now a mandatory delivery gate: no handover without a PASS against the folder
  the photographer actually looks at; the PASS report is part of the handover.

## raw-to-jpeg 3.3.0 — 2026-11-20 (print-business review of Laikipia)

### Fixed
- Auto exposure blew out bright / hazy / sunlit scenes (Laikipia _U4A8533 at +2.15 EV, _U4A8603,
  sunlit rhinos): highlights are now capped at the camera's own p95 (max 238, <0.3 % clipped) and
  high-key scenes get no extra brightening. Low-key scenes unchanged (_U4A0059 approved result kept).
- Glow halos along subject edges against bright backgrounds: tighter edge-aware tone mapping
  (eps 0.25 -> 0.06) and the finish's light pool now fades where the background is brighter than
  the animal (Laikipia _U4A8380 rhinos).
- Blue shadows on grey animals (shade WB + vibrance): blue-leaning darks are pulled to neutral.

### Added
- Print-worthy selection rules in the workflow (wall-print standard, no hidden faces, no backs,
  no look-aways, no redundancy, crop distractions, separate camouflaged subjects).
- tools/retouch_blade.py — texture-preserving removal of a grass blade across a face.
- tools/separate_subject.py — lens-like, distance-graded background blur behind a masked subject.

## raw-to-jpeg 3.2.0 — 2026-11-20 13:40 PST

### Changed
- best_shots.py picks per MOMENT (≤20 s, similar composition), not per sighting; focus compared only
  within a burst; numbered contact sheets + `--keep` for a story-first visual review; `--auto` for
  unattended runs. Story rules (mother & young, behaviour, herds, motion, eye contact, rare animals,
  dramatic light) added to the workflow. Fixes all 13 misses on the 2026 Laikipia shoot.

## raw-to-jpeg 3.1.0 — 2026-11-20 12:40 PST

### Added
- `tools/best_shots.py` (stage 0): one best frame per sighting → `<shoot>/Best Images` (RAW + camera JPG,
  `best_shots_log.csv`, review contact sheet), using the approved Laikipia selection rules.
- `--skip-pick` (process an existing Best Images folder) and `--all` (no picking).

### Changed
- Default layout: originals stay in the shoot folder; picks in `Best Images/`, finished JPEGs in `Processed/`.

## raw-to-jpeg 3.0.0 "final" — 2026-11-20 10:22 PST

Rebuilt as a four-stage pipeline that reproduces the approved final of `_U4A0059`
(Laikipia leopard, 2026) end to end.

### Added
- `tools/photo_develop.py` + `tools/calib.json` — house look learned from the photographer's own
  Adobe Camera Raw edit (PV 15.4, Adobe Color), calibrated slider gains + residual look LUT,
  guided-filter highlights/shadows, auto exposure relative to the camera preview (+12 % median),
  crop before develop, detail-aware denoise with dither, lossless PNG output.
- `tools/expert_finish.py` — GrabCut subject mask (box or automatic saliency), calmer background,
  subject dodge with darks protected, local WB for shaded fur, face clarity + eye lift, neutral
  dark markings.
- `tools/upscale_print.py` — 3× print master (largest useful size): defringe, Lanczos in 2× steps,
  luminance-only detail-masked USM, 300 ppi.
- `tools/sign_image.py` — signature bottom-right on copies in `signed/`; signature PNGs kept
  outside the public repo (`--sig-dir` / `RTJ_SIGNATURE_DIR`).
- Per-image `--plan` JSON (exposure, crop, subject, face).
- Mandatory review-before-hand-over step in the workflow.

### Changed
- `tools/raw_to_jpeg.py` is now the pipeline orchestrator (v3).
- Workflow, slash command and README rewritten.
- Requirements: added `opencv-contrib-python-headless`.

### Moved
- v1 tool and Photoshop JSX → `tools/legacy/`.

## raw-to-jpeg 1.x
- rawpy processor with auto-brightness, auto-crop and vivid defaults (see `tools/legacy/`).
