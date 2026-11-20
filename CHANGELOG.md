# Changelog

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
