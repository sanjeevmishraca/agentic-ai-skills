"""Remove a grass blade (thin light band) from fur, texture-preserving.

Low frequencies (colour, spot shapes) come from a smooth fill across the band; high frequencies
(fur grain) are copied from fur just beside the band, shifted perpendicular to it. That keeps the
fur texture instead of the smear a plain inpaint gives."""
import sys, numpy as np, cv2
from PIL import Image

def remove(img, path, width=34):
    H, W = img.shape[:2]
    m = np.zeros((H, W), np.uint8)
    cv2.polylines(m, [path.astype(np.int32)], False, 255, thickness=width)
    x0, y0 = max(0, int(path[:, 0].min()) - 160), max(0, int(path[:, 1].min()) - 40)
    x1, y1 = min(W, int(path[:, 0].max()) + 160), min(H, int(path[:, 1].max()) + 40)
    crop = img[y0:y1, x0:x1].astype(np.float32); mm = m[y0:y1, x0:x1]
    # low-frequency fill: Telea on a blurred copy (no texture to smear)
    # fill from pixels clear of the blade's soft glow (mask dilated), then blur -> colour/tone only
    big = cv2.dilate(mm, np.ones((15, 15), np.uint8))
    filled = cv2.inpaint(crop.astype(np.uint8), big, 25, cv2.INPAINT_TELEA).astype(np.float32)
    low = cv2.GaussianBlur(crop, (0, 0), 3)
    low_fill = cv2.GaussianBlur(filled, (0, 0), 3)
    # high-frequency donor: fur on either side of the band, shifted horizontally across it
    high = crop - low
    shift = width + 6
    left = np.roll(high, shift, axis=1); right = np.roll(high, -shift, axis=1)
    ml = np.roll(mm, shift, axis=1); mr = np.roll(mm, -shift, axis=1)
    donor = np.where((ml == 0)[..., None], left, right)
    donor = np.where(((ml > 0) & (mr > 0))[..., None], 0, donor)
    rebuilt = low_fill + donor
    soft = cv2.GaussianBlur(mm.astype(np.float32) / 255, (0, 0), 2.5)[..., None]
    out = img.copy()
    out[y0:y1, x0:x1] = np.clip(rebuilt * soft + crop * (1 - soft), 0, 255).astype(np.uint8)
    return out

if __name__ == '__main__':
    src, dst = sys.argv[1], sys.argv[2]
    # path: .npy of (x, y) points along the blade, in 6000-px-wide frame coordinates
    path = np.load(sys.argv[3])
    pil = Image.open(src); info = {k: pil.info[k] for k in ('icc_profile', 'exif', 'dpi') if k in pil.info}
    img = np.asarray(pil.convert('RGB'))
    s = img.shape[1] / 6000.0
    out = remove(img, path * s, max(8, int(46 * s)))
    Image.fromarray(out).save(dst, 'JPEG', quality=97, subsampling=0, **info)
    print('saved', dst)
