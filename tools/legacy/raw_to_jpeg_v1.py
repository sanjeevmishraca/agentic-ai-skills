#!/usr/bin/env python3
"""
raw_to_jpeg.py
──────────────
WAT Framework Tool – RAW Image → JPEG Processor

Uses rawpy (LibRaw engine – same core as Adobe Camera Raw 18) to batch-convert
RAW camera files to high-quality JPEGs with full tone and colour adjustments.
Fully headless – no GUI or Adobe application required at runtime.

Usage
-----
python tools/raw_to_jpeg.py --input  <folder_or_zip>
                             --output <output_folder>    (default: <input>/Processed)
                             --settings <json_string>    (optional Camera Raw overrides)

Settings JSON keys (all optional – defaults applied if omitted):
  jpegQuality          1-12              default: 10
  colorSpace           sRGB|AdobeRGB     default: sRGB
  resolution           int (DPI)         default: 300
  whiteBalance         asShot|auto|daylight|cloudy|shade|tungsten|fluorescent|flash|custom
  temperature          int (K)           only when whiteBalance=custom
  tint                 int               only when whiteBalance=custom (ignored by LibRaw)
  auto_brightness      bool              default: True  — per-image histogram analysis for exposure
  exposure             float -4.0..4.0   default: 0.0   — fine-tune offset applied on top of auto_brightness
  contrast             int -50..100      default: 30
  highlights           int -100..100     default: 0
  shadows              int -100..100     default: 0
  whites               int -100..100     default: 0
  blacks               int -100..100     default: 0
  clarity              int -100..100     default: 25
  saturation           int -100..100     default: 15
  vibrance             int -100..100     default: 30
  sharpness            int 0..100        default: 55
  luminanceSmoothing   int 0..100        default: 0
  colorNoiseReduction  int 0..100        default: 25
  auto_crop            bool              default: True  — detect & crop edge-clipped subjects

Exit codes: 0 success | 1 bad args | 2 no RAW files | 4 partial failures
"""

import argparse
import json
import os
import sys
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter

try:
    import rawpy
except ImportError:
    print("ERROR: rawpy not installed. Run: pip install rawpy Pillow")
    sys.exit(1)

# ─── Constants ────────────────────────────────────────────────────────────────

RAW_EXTENSIONS = {
    ".cr2", ".cr3",
    ".nef", ".nrw",
    ".arw", ".srf", ".sr2",
    ".raf",
    ".dng",
    ".orf",
    ".rw2",
    ".pef",
    ".srw",
    ".3fr",
    ".mef",
    ".mrw",
    ".rwl",
    ".x3f",
    ".erf",
}

DEFAULT_SETTINGS = {
    "jpegQuality":          10,
    "colorSpace":           "sRGB",
    "resolution":           300,
    "whiteBalance":         "asShot",
    "temperature":          None,
    "tint":                 None,
    "auto_brightness":      True,  # per-image histogram-based exposure
    "exposure":             0.0,   # fine-tune offset on top of auto_brightness
    "contrast":             30,    # user preferred: more punch
    "highlights":           0,
    "shadows":              0,
    "whites":               0,
    "blacks":               0,
    "clarity":              25,    # user preferred: more punch
    "saturation":           15,    # user preferred: vibrant
    "vibrance":             30,    # user preferred: vibrant
    "sharpness":            55,    # user preferred: sharper
    "luminanceSmoothing":   0,
    "colorNoiseReduction":  25,
    "auto_crop":            True,  # crop edge-clipped subjects
}

TMP_DIR = Path(__file__).parent.parent / ".tmp"

# ─── Tone adjustment helpers ──────────────────────────────────────────────────

def _lut_from_points(points: list) -> np.ndarray:
    """Build a 256-entry uint8 LUT by interpolating through (x, y) control points."""
    xs = np.array([p[0] for p in points], dtype=np.float32)
    ys = np.array([p[1] for p in points], dtype=np.float32)
    lut = np.interp(np.arange(256, dtype=np.float32), xs, ys)
    return np.clip(lut, 0, 255).astype(np.uint8)


def apply_tone_curve(arr: np.ndarray, settings: dict) -> np.ndarray:
    """
    Build a combined per-channel LUT encoding exposure, contrast,
    highlights, shadows, whites, and blacks.
    """
    exposure  = float(settings.get("exposure",   0.0))
    contrast  = float(settings.get("contrast",   0))
    highlight = float(settings.get("highlights", 0))
    shadow    = float(settings.get("shadows",    0))
    whites    = float(settings.get("whites",     0))
    blacks    = float(settings.get("blacks",     0))

    # Start with identity curve
    x = np.arange(256, dtype=np.float32)
    y = x.copy()

    # Exposure: EV shift → linear multiplier applied before gamma
    if exposure != 0:
        mult = 2.0 ** exposure
        y = np.clip(y * mult, 0, 255)

    # Blacks: lift/crush the black point (0–255 range input → 0..50 raise or lower)
    if blacks != 0:
        shift = blacks * 0.5          # ±50 → ±25 out of 255
        y = np.clip(y + shift * (1 - x / 255), 0, 255)

    # Whites: raise/lower the white point
    if whites != 0:
        scale = 1.0 + whites / 400.0  # ±100 → ±25% white point shift
        y = np.clip(y * scale, 0, 255)

    # Shadows: lift or deepen shadow tones (values < 128)
    if shadow != 0:
        mask = (x / 255) ** 2         # weight towards shadows
        y = np.clip(y + shadow * 0.4 * mask * (1 - x / 255), 0, 255)

    # Highlights: compress or boost highlight tones (values > 128)
    if highlight != 0:
        mask = (x / 255) ** 2         # weight towards highlights
        y = np.clip(y + highlight * 0.4 * mask * (x / 255), 0, 255)

    # Contrast: S-curve around midpoint 128
    if contrast != 0:
        factor = contrast / 200.0     # ±100 → ±0.5
        mid = 128.0
        y = np.clip(mid + (y - mid) * (1 + factor), 0, 255)

    lut = np.clip(y, 0, 255).astype(np.uint8)
    # Apply LUT to all channels
    return lut[arr]


def apply_saturation_vibrance(img: Image.Image, saturation: float, vibrance: float) -> Image.Image:
    """
    Saturation: uniform colour boost.
    Vibrance: boosts less-saturated colours more (like ACR vibrance).
    """
    if saturation == 0 and vibrance == 0:
        return img

    # Convert to numpy HSV via float
    arr = np.array(img, dtype=np.float32) / 255.0
    r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]

    cmax = np.maximum(np.maximum(r, g), b)
    cmin = np.minimum(np.minimum(r, g), b)
    delta = cmax - cmin
    eps = 1e-6

    # Saturation in HSV space
    s = np.where(cmax > eps, delta / (cmax + eps), 0.0)

    if saturation != 0:
        sat_factor = 1.0 + saturation / 100.0
        sat_factor = max(0.0, sat_factor)
        # Blend towards grey using saturation factor
        grey = (r + g + b) / 3.0
        arr[..., 0] = np.clip(grey + (r - grey) * sat_factor, 0, 1)
        arr[..., 1] = np.clip(grey + (g - grey) * sat_factor, 0, 1)
        arr[..., 2] = np.clip(grey + (b - grey) * sat_factor, 0, 1)

    if vibrance != 0:
        # Vibrance: stronger effect on less-saturated pixels
        vib_factor = vibrance / 100.0
        low_sat_weight = 1.0 - s          # high weight for low-saturation pixels
        vib_mult = 1.0 + vib_factor * low_sat_weight
        grey = (arr[..., 0] + arr[..., 1] + arr[..., 2]) / 3.0
        for ch in range(3):
            arr[..., ch] = np.clip(
                grey + (arr[..., ch] - grey) * vib_mult, 0, 1
            )

    return Image.fromarray((arr * 255).astype(np.uint8))


def apply_clarity(img: Image.Image, amount: float) -> Image.Image:
    """
    Clarity: local contrast enhancement on midtones.
    Positive → crunch midtone detail; negative → soft/glow.
    """
    if amount == 0:
        return img
    radius = 10
    scale = abs(amount) / 100.0
    blurred = img.filter(ImageFilter.GaussianBlur(radius=radius))
    arr_orig   = np.array(img,     dtype=np.float32)
    arr_blur   = np.array(blurred, dtype=np.float32)
    detail     = arr_orig - arr_blur           # high-frequency detail
    if amount > 0:
        result = arr_orig + detail * scale * 0.5
    else:
        result = arr_orig - detail * scale * 0.5
    return Image.fromarray(np.clip(result, 0, 255).astype(np.uint8))


def apply_sharpness(img: Image.Image, amount: float) -> Image.Image:
    """Unsharp mask sharpening scaled 0–100."""
    if amount <= 0:
        return img
    factor = 1.0 + (amount / 50.0)   # 25 → factor 1.5; 100 → factor 3.0
    return ImageEnhance.Sharpness(img).enhance(factor)


# ─── Auto brightness ─────────────────────────────────────────────────────────

def calculate_auto_exposure(arr: np.ndarray) -> float:
    """
    Analyse a rendered image array (typically half-size for speed) and return
    the optimal EV adjustment so highlights are protected and midtones are natural.

    Strategy:
      - Keep P98 luminance at 225  (protects highlights / sky)
      - Also target P50 (median) at 115  (natural outdoor midtone)
      - If both can be satisfied, blend them; if highlights would clip, prioritise P98.
    """
    lum = (0.2126 * arr[:, :, 0].astype(np.float64) +
           0.7152 * arr[:, :, 1].astype(np.float64) +
           0.0722 * arr[:, :, 2].astype(np.float64))

    p50 = float(np.percentile(lum, 50))
    p98 = float(np.percentile(lum, 98))

    TARGET_P98 = 225.0   # near-white point target
    TARGET_P50 = 115.0   # natural midtone

    ev_hi  = np.log2(TARGET_P98 / p98) if p98 > 1 else 0.0
    ev_mid = np.log2(TARGET_P50 / p50) if p50 > 1 else 0.0

    # If midtone target would blow highlights, use highlight-safe EV
    if p98 * (2.0 ** ev_mid) > 245.0:
        ev = ev_hi
    else:
        # Blend: prioritise highlight safety (70%) over midtone brightness (30%)
        ev = ev_hi * 0.70 + ev_mid * 0.30

    ev = float(np.clip(ev, -3.0, 3.0))
    print(f"[raw_to_jpeg]   Auto-brightness: P50={p50:.0f} P98={p98:.0f} -> EV {ev:+.2f}")
    return ev


# ─── Auto crop ────────────────────────────────────────────────────────────────

def auto_crop_edge_subjects(img: Image.Image, max_crop_pct: float = 0.25) -> Image.Image:
    """
    Detect and remove subjects that are clipped (cut off) at any image edge.

    Method: corner-based background estimation.
      1. Sample the four corner regions — these are almost always sky/ground/background.
      2. Build a statistical model of the background colour.
      3. For each edge, scan inward column by column; a column where >SUBJECT_FRAC of
         pixels deviate significantly from background = a subject touching the edge.
      4. Find the first gap (run of background-like columns) after that subject zone.
      5. Crop to that gap point so the clipped subject is removed.
    """
    w, h = img.size

    # Work at ~500px wide for speed
    scale = min(1.0, 500.0 / w)
    sw, sh = max(1, int(w * scale)), max(1, int(h * scale))
    small = np.array(img.resize((sw, sh), Image.LANCZOS), dtype=np.float32) / 255.0

    # Use the relevant image dimension for each scan direction
    # (width for left/right, height for top/bottom) so a tall thin sliver
    # on a wide image doesn't get under-scanned.
    max_px_x = max(8, int(sw * max_crop_pct))   # cols scanned from left or right
    max_px_y = max(8, int(sh * max_crop_pct))   # rows scanned from top or bottom
    c_sz     = max(5, int(min(sw, sh) * 0.05))  # corner sample size

    # Characterise background from corners
    corners = np.concatenate([
        small[:c_sz,  :c_sz,  :].reshape(-1, 3),
        small[:c_sz,  -c_sz:, :].reshape(-1, 3),
        small[-c_sz:, :c_sz,  :].reshape(-1, 3),
        small[-c_sz:, -c_sz:, :].reshape(-1, 3),
    ])
    bg_mean = corners.mean(axis=0)
    bg_std  = corners.std(axis=0).clip(min=0.04)   # minimum spread prevents over-sensitivity

    def non_bg_fraction(pixels: np.ndarray) -> float:
        """Fraction of pixels that differ significantly from the background model."""
        diff = np.abs(pixels - bg_mean) / bg_std
        return float(np.mean(np.any(diff > 2.8, axis=-1)))

    SUBJECT_FRAC = 0.18   # >18% non-bg pixels in a slice -> subject present at edge
    # GAP_FRAC calibration:
    #   Very fine appendages (tail hair tips, fur wisps) appear at 1.5-4% non-bg fraction.
    #   Thin appendages (tails, ears, wingtips) appear as 5-7% non-bg fraction.
    #   Setting to 0.02 ensures even the finest hair/fur tips are treated as SUBJECT,
    #   pushing the crop point fully past all trace of the clipped subject.
    GAP_FRAC  = 0.02
    # GAP_WIDTH calibration:
    #   Gaps between animal legs/limbs at full res ≈ 80-150px
    #   At 500px working width (scale≈0.091) that is ≈ 7-14 scaled columns.
    #   Real background zone between subjects is ≈ 200-400px → 18-36 scaled columns.
    #   Setting GAP_WIDTH=16 safely skips leg-gaps while still finding real background.
    GAP_WIDTH = 16

    def find_gap(profile: list) -> int:
        """
        Return scaled-px offset to crop at.
        Scans for the FIRST run of GAP_WIDTH consecutive background-level columns —
        wide enough to skip gaps between animal legs but narrow enough to find the
        actual background zone between subjects.
        """
        if not profile or profile[0] < SUBJECT_FRAC:
            return 0
        for i in range(1, len(profile) - GAP_WIDTH + 1):
            if all(profile[i + j] < GAP_FRAC for j in range(GAP_WIDTH)):
                return i
        return 0

    left_p  = [non_bg_fraction(small[:, x,      :]) for x in range(max_px_x)]
    right_p = [non_bg_fraction(small[:, sw-1-x, :]) for x in range(max_px_x)]
    top_p   = [non_bg_fraction(small[y,      :, :]) for y in range(max_px_y)]
    bot_p   = [non_bg_fraction(small[sh-1-y, :, :]) for y in range(max_px_y)]

    left  = int(find_gap(left_p)  / scale)
    right = w - int(find_gap(right_p) / scale)
    top   = int(find_gap(top_p)   / scale)
    bot   = h - int(find_gap(bot_p)   / scale)

    if left > 0 or right < w or top > 0 or bot < h:
        print(f"[raw_to_jpeg]   Auto-crop: L+{left}px  R-{w - right}px  T+{top}px  B-{h - bot}px")
        return img.crop((left, top, right, bot))

    return img


# ─── White balance → rawpy params ────────────────────────────────────────────

# Approximate daylight multipliers for common preset temperatures
_WB_PRESETS = {
    "daylight":    (6500, [2.0, 1.0, 1.5, 1.0]),
    "cloudy":      (7000, [2.1, 1.0, 1.4, 1.0]),
    "shade":       (8000, [2.3, 1.0, 1.3, 1.0]),
    "tungsten":    (3200, [1.4, 1.0, 2.4, 1.0]),
    "fluorescent": (4000, [1.7, 1.0, 2.0, 1.0]),
    "flash":       (5500, [1.95, 1.0, 1.6, 1.0]),
}


def build_rawpy_params(settings: dict, exposure_ev: float = None) -> dict:
    """
    Map settings dict to rawpy.postprocess() kwargs.
    exposure_ev overrides settings["exposure"] when provided (used by auto_brightness).
    """
    wb = settings.get("whiteBalance", "asShot").lower().replace(" ", "")
    params = {
        "output_color":   rawpy.ColorSpace.sRGB,
        "output_bps":     8,
        "no_auto_bright": True,
        "bright":         1.0,
    }

    if wb == "asshot":
        params["use_camera_wb"] = True
    elif wb == "auto":
        params["use_auto_wb"] = True
    elif wb in _WB_PRESETS:
        params["user_wb"] = _WB_PRESETS[wb][1]
    elif wb == "custom" and settings.get("temperature"):
        temp = float(settings["temperature"])
        if temp < 4000:
            r_m = 1.3 + (4000 - temp) / 4000
            b_m = 2.5 - (4000 - temp) / 4000
        else:
            r_m = 1.3 + (temp - 4000) / 8000
            b_m = max(0.8, 2.5 - (temp - 4000) / 6000)
        params["user_wb"] = [r_m, 1.0, b_m, 1.0]
    else:
        params["use_camera_wb"] = True

    # Positive EV shifts handled via rawpy exp_shift; negatives via tone curve
    ev = exposure_ev if exposure_ev is not None else float(settings.get("exposure", 0.0))
    if ev > 0:
        params["exp_shift"] = 2.0 ** ev

    nr = int(settings.get("colorNoiseReduction", 25))
    ln = int(settings.get("luminanceSmoothing",  0))
    if max(nr, ln) > 50:
        params["fbdd_noise_reduction"] = rawpy.FBDDNoiseReductionMode.Full
    elif max(nr, ln) > 20:
        params["fbdd_noise_reduction"] = rawpy.FBDDNoiseReductionMode.Light
    else:
        params["fbdd_noise_reduction"] = rawpy.FBDDNoiseReductionMode.Off

    return params


# ─── Core processor ──────────────────────────────────────────────────────────

def process_raw_file(raw_path: str, output_path: str, settings: dict):
    """Convert a single RAW file to JPEG with the given settings."""

    # ── Step 1: determine exposure EV ────────────────────────────────────────
    use_auto_brightness = settings.get("auto_brightness", True)
    base_ev = float(settings.get("exposure", 0.0))   # user fine-tune offset

    if use_auto_brightness:
        # Half-size probe render (fast) to analyse histogram
        with rawpy.imread(raw_path) as raw:
            probe_params = build_rawpy_params(settings, exposure_ev=0.0)
            probe_params["half_size"] = True
            probe_rgb = raw.postprocess(**probe_params)
        auto_ev = calculate_auto_exposure(probe_rgb)
        final_ev = float(np.clip(auto_ev + base_ev, -3.0, 3.0))
        print(f"[raw_to_jpeg]   Final EV: auto({auto_ev:+.2f}) + offset({base_ev:+.2f}) = {final_ev:+.2f}")
    else:
        final_ev = base_ev

    # ── Step 2: full-size render with computed EV ─────────────────────────────
    with rawpy.imread(raw_path) as raw:
        params = build_rawpy_params(settings, exposure_ev=final_ev)
        rgb = raw.postprocess(**params)

    img = Image.fromarray(rgb)

    # ── Step 3: tone curve (remaining EV for negatives, contrast, hi/shadows) -
    # If final_ev was positive it was applied via exp_shift in rawpy already;
    # pass 0 so the tone curve doesn't double-apply it.
    tone_settings = dict(settings)
    tone_settings["exposure"] = 0.0 if final_ev >= 0 else final_ev
    arr = np.array(img, dtype=np.uint8)
    arr = apply_tone_curve(arr, tone_settings)
    img = Image.fromarray(arr)

    # ── Step 4: saturation / vibrance ─────────────────────────────────────────
    img = apply_saturation_vibrance(
        img,
        float(settings.get("saturation", 0)),
        float(settings.get("vibrance",   0)),
    )

    # ── Step 5: clarity ───────────────────────────────────────────────────────
    img = apply_clarity(img, float(settings.get("clarity", 0)))

    # ── Step 6: sharpness ─────────────────────────────────────────────────────
    img = apply_sharpness(img, float(settings.get("sharpness", 25)))

    # ── Step 7: auto-crop edge-clipped subjects ───────────────────────────────
    if settings.get("auto_crop", True):
        img = auto_crop_edge_subjects(img)

    # ── Step 8: save JPEG ─────────────────────────────────────────────────────
    cr_quality   = int(settings.get("jpegQuality", 10))
    jpeg_quality = max(1, min(95, int((cr_quality / 12) * 95)))
    dpi          = int(settings.get("resolution", 300))
    img.save(output_path, "JPEG", quality=jpeg_quality, dpi=(dpi, dpi),
             optimize=True, subsampling=0)


# ─── Input helpers ────────────────────────────────────────────────────────────

def extract_zip(zip_path: str, dest_dir: str) -> str:
    print(f"[raw_to_jpeg] Extracting zip: {zip_path}")
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(dest_dir)
    return dest_dir


def find_raw_files(folder: str) -> list:
    found = []
    for root, _, files in os.walk(folder):
        for f in files:
            if Path(f).suffix.lower() in RAW_EXTENSIONS:
                found.append(os.path.join(root, f))
    return found


def merge_settings(overrides: dict) -> dict:
    settings = dict(DEFAULT_SETTINGS)
    for k, v in overrides.items():
        if k in settings:
            settings[k] = v
        elif k in ("auto_brightness", "auto_crop"):   # booleans accepted even if not in defaults
            settings[k] = bool(v)
        else:
            print(f"[raw_to_jpeg] WARNING: Unknown setting '{k}' ignored.")
    return settings


def print_summary(processed: list, failed: list, total: int, output_folder: str):
    print("\n" + "=" * 60)
    print("  RAW -> JPEG Processing Complete  (rawpy / LibRaw engine)")
    print("=" * 60)
    print(f"  Total RAW files :  {total}")
    print(f"  Processed       :  {len(processed)}")
    print(f"  Failed          :  {len(failed)}")
    print(f"  Output folder   :  {output_folder}")
    if processed:
        print("\n  Processed files:")
        for p in processed:
            print(f"    OK  {Path(p).name}")
    if failed:
        print("\n  Failed files:")
        for item in failed:
            print(f"    FAIL  {item['file']}  -  {item['error']}")
    print("=" * 60 + "\n")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Convert RAW images to JPEG using rawpy (LibRaw / Camera Raw engine)."
    )
    parser.add_argument("--input",    "-i", required=True,
                        help="Folder of RAW files or a .zip archive.")
    parser.add_argument("--output",   "-o",
                        default=None,
                        help="Output folder for JPEGs. Default: <input>/Processed")
    parser.add_argument("--settings", "-s", default="{}",
                        help='JSON Camera Raw settings override string.')
    args = parser.parse_args()

    # ── Resolve input
    input_path = os.path.abspath(args.input)
    if not os.path.exists(input_path):
        print(f"[raw_to_jpeg] ERROR: Input path does not exist: {input_path}")
        sys.exit(1)

    work_folder = input_path
    if os.path.isfile(input_path) and input_path.lower().endswith(".zip"):
        extract_dir = str(TMP_DIR / "raw_extracted")
        os.makedirs(extract_dir, exist_ok=True)
        extract_zip(input_path, extract_dir)
        work_folder = extract_dir

    # ── Find RAW files
    raw_files = find_raw_files(work_folder)
    if not raw_files:
        print(f"[raw_to_jpeg] ERROR: No RAW files found in: {work_folder}")
        print(f"[raw_to_jpeg] Supported: {', '.join(sorted(RAW_EXTENSIONS))}")
        sys.exit(2)
    print(f"[raw_to_jpeg] Found {len(raw_files)} RAW file(s)")

    # ── Resolve output
    if args.output is None:
        args.output = str(Path(work_folder) / "Processed")
    output_folder = os.path.abspath(args.output)
    os.makedirs(output_folder, exist_ok=True)
    print(f"[raw_to_jpeg] Output: {output_folder}")

    # ── Parse settings
    try:
        overrides = json.loads(args.settings)
    except json.JSONDecodeError as e:
        print(f"[raw_to_jpeg] ERROR: Invalid --settings JSON: {e}")
        sys.exit(1)

    settings = merge_settings(overrides)
    print(f"[raw_to_jpeg] Settings: {json.dumps({k: v for k, v in settings.items() if v is not None}, indent=2)}")

    # ── Process files
    processed, failed = [], []
    for i, raw_path in enumerate(raw_files, 1):
        name = Path(raw_path).name
        out_name = Path(raw_path).stem + ".jpg"
        out_path = os.path.join(output_folder, out_name)
        print(f"[raw_to_jpeg] ({i}/{len(raw_files)}) {name} -> {out_name}")
        try:
            process_raw_file(raw_path, out_path, settings)
            processed.append(out_path)
            print(f"[raw_to_jpeg]   OK saved")
        except Exception as e:
            print(f"[raw_to_jpeg]   ✗ FAILED: {e}")
            failed.append({"file": name, "error": str(e)})

    # ── Write results JSON (for compatibility with existing workflow)
    results_path = TMP_DIR / "raw_processing_results.json"
    results_path.parent.mkdir(parents=True, exist_ok=True)
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump({"processed": processed, "failed": failed, "total": len(raw_files)}, f, indent=2)

    print_summary(processed, failed, len(raw_files), output_folder)
    sys.exit(4 if failed else 0)


if __name__ == "__main__":
    main()
