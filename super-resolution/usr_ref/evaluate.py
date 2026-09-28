"""Mesure de la qualite : on compare chaque methode a la verite terrain.

* PSNR (dB) sur l'image compressee [0, 1] : plus haut = plus fidele ;
* scintillement : ecart entre la variation d'une image a la suivante et
  celle de la verite terrain. Plus bas = plus stable (c'est ce qui se voit
  le plus en jeu : grillages et cables qui clignotent).
"""

import struct
import zlib

import numpy as np

from . import core
from .scene import Scene


def psnr(out, gt):
    mse = np.mean((core.tonemap(out) - core.tonemap(gt)) ** 2)
    return float(10.0 * np.log10(1.0 / max(mse, 1e-12)))


def bilinear_upscale(img, size):
    w, h = size
    ys, xs = np.mgrid[0:h, 0:w]
    return core.sample_bilinear(img, (xs + 0.5) / w, (ys + 0.5) / h)


def run(scene, display_size, mode="performance", frames=48, method="ia",
        network=None, sharpness=0.0, t0=0.0, keep=()):
    """Joue une sequence et renvoie les metriques (et les images demandees).

    method : ``bilineaire`` (sans jitter, sans historique), ``heuristique``
    (USR sans reseau) ou ``ia`` (USR complet).
    """
    rsize = core.render_size(display_size, mode)
    phases = core.jitter_phase_count(rsize[0], display_size[0])
    up = core.Upscaler(rsize, display_size,
                       network=network if method == "ia" else None)
    warmup = min(8, frames // 2)
    scores, flicker, kept = [], [], {}
    prev_out = prev_gt = None
    for f in range(frames):
        t = t0 + f
        gt = scene.ground_truth(t, display_size)
        if method == "bilineaire":
            color, _, _ = scene.render(t, rsize)
            out = bilinear_upscale(color, display_size)
        else:
            jitter = core.jitter_offset(f, phases)
            color, invz, motion = scene.render(t, rsize, jitter)
            out = up.dispatch(color, invz, motion, jitter,
                              sharpness=sharpness)
        if f >= warmup:
            scores.append(psnr(out, gt))
            if prev_out is not None:
                d_out = core.tonemap(out) - core.tonemap(prev_out)
                d_gt = core.tonemap(gt) - core.tonemap(prev_gt)
                flicker.append(float(np.mean(np.abs(d_out - d_gt))))
        if f in keep:
            kept[f] = (out, gt)
        prev_out, prev_gt = out, gt
    return {
        "psnr": float(np.mean(scores)),
        "scintillement": float(np.mean(flicker)) if flicker else 0.0,
        "images": kept,
    }


def benchmark(network, display_size=(256, 144), frames=40, modes=(
        "performance",), seeds=(101, 202), log=print):
    """Tableau comparatif sur des scenes jamais vues a l'entrainement."""
    rows = []
    for mode in modes:
        for seed in seeds:
            for static in (True, False):
                scene = Scene(seed=seed, static=static, cache_gt=True)
                row = {"mode": mode, "scene": seed,
                       "camera": "fixe" if static else "mobile"}
                for method in ("bilineaire", "heuristique", "ia"):
                    if method == "ia" and network is None:
                        continue
                    r = run(scene, display_size, mode, frames, method,
                            network)
                    row[method] = (r["psnr"], r["scintillement"])
                rows.append(row)
                log(format_row(row))
    return rows


def format_row(row):
    cells = ["%-11s %-6s scene %-4s" % (row["mode"], row["camera"],
                                        row["scene"])]
    for method in ("bilineaire", "heuristique", "ia"):
        if method in row:
            p, s = row[method]
            cells.append("%s %5.2f dB / %.4f" % (method, p, s))
    return " | ".join(cells)


# --------------------------------------------------------------------------
# PNG sans dependance (pour regarder les resultats)
# --------------------------------------------------------------------------

def to_srgb8(img):
    y = np.clip(core.tonemap(np.maximum(img, 0.0)), 0.0, 1.0)
    return (np.power(y, 1.0 / 2.2) * 255.0 + 0.5).astype(np.uint8)


def write_png(path, img8):
    h, w = img8.shape[:2]
    raw = b"".join(b"\x00" + img8[y].tobytes() for y in range(h))

    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
        f.write(chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)))
        f.write(chunk(b"IDAT", zlib.compress(raw, 9)))
        f.write(chunk(b"IEND", b""))


def zoom(img8, factor):
    return np.repeat(np.repeat(img8, factor, axis=0), factor, axis=1)
