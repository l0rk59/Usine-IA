"""Banc de mesure de USR Universel : le tableau de docs/UNIVERSEL.md.

    python -m usr_ref universel-banc            # tout (une vingtaine de min)
    python -m usr_ref universel-banc --rapide   # scene 101, rapport 2

Scenario « jeu emule » (usr_ref/emul.py) : le jeu est rendu a basse
resolution, HUD compris, compresse pour l'ecran et range sur 8 bits ; la
verite terrain est le meme jeu rendu directement a la resolution
d'affichage. Scenes jamais vues a l'entrainement (graines 101 et 202 ;
l'entrainement utilise 1 a 9).

Pour chaque sequence (32 images, les 8 premieres ne comptent pas : le
temps que l'historique se remplisse) : PSNR et SSIM sur l'image affichee,
scintillement = moyenne de |variation de la sortie - variation de la
verite| d'une image a la suivante ; et les memes mesures par region
(fond fixe, ecrans animes, objets, HUD).

Niveau 0 : agrandissements sans historique (bilineaire, Lanczos, spatial
type FSR 1). Niveau 1 : USR Universel sur l'image telle quelle. Niveau 2 :
l'emulateur injecte un jitter en grille (HUD non decale), avec ou sans
biais de mip-map -1 (« lod-1 »).
"""

import json

import numpy as np

from . import emul, evaluate, universel
from .scene import Scene
from .scene_realiste import RealisticScene

DISPLAY = (384, 216)
RENDER = {2: (192, 108), 3: (128, 72)}
FRAMES = 32
WARM = 8
SCENES = (("real", 101, False), ("real", 101, True), ("real", 202, False),
          ("brut", 101, False))


def _scene(kind, seed, static):
    return (RealisticScene if kind == "real" else Scene)(seed=seed,
                                                         static=static)


def sequence(kind, seed, static, render_size, jitter="aucun", lod=0.0,
             frames=FRAMES, display_size=DISPLAY):
    """Images du jeu emule (h, w, 3), jitters et verites terrain."""
    game = emul.EmulatedGame(_scene(kind, seed, static))
    jit, _ = universel.jitter_plan(render_size, display_size, jitter)
    items = []
    for f in range(frames):
        j = jit(f)
        img, _, _ = game.frame(float(f), render_size, j, lod_bias=lod,
                               hud_jitter=False)
        items.append((img, j, game.truth(float(f), display_size)))
    return items


_REGIONS = {}


def regions(kind, seed, static, f, display_size=DISPLAY):
    """Masques d'affichage : fond fixe, ecrans / neon animes, objets, HUD."""
    key = (kind, seed, static, f, tuple(display_size))
    if key not in _REGIONS:
        _REGIONS[key] = _regions(kind, seed, static, f, display_size)
    return dict(_REGIONS[key])


def _regions(kind, seed, static, f, display_size):
    sc = _scene(kind, seed, static)
    game = emul.EmulatedGame(sc)
    _, invz, _ = game.frame(float(f), display_size)
    dw, dh = display_size
    oy, ox = np.mgrid[0:dh, 0:dw]
    u = (ox + 0.5) / dw
    v = (oy + 0.5) / dh
    bg = np.abs(invz - 0.05) < 1e-6
    hud = invz > 0.99
    obj = ~bg & ~hud
    if kind == "real":
        cam = sc.camera(float(f))
        px = (u * sc.aspect + cam[0]) % 1.7
        py = (v + cam[1]) % 1.3
        anim = bg & ((((px > 0.88) & (px < 1.47)) & ((py > 0.23) & (py < 0.62)))
                     | (((px > 0.18) & (px < 0.72))
                        & (np.abs(py - 0.95) < 0.03)))
    else:
        anim = np.zeros_like(bg)
    return {"fond": bg & ~anim, "anime": anim, "objets": obj, "hud": hud}


def ssim_map(a, b):
    """SSIM par pixel (moyenne des canaux), fenetre gaussienne de emul."""
    a = np.asarray(a, np.float64)
    b = np.asarray(b, np.float64)
    c1, c2 = 0.01 ** 2, 0.03 ** 2
    blur = emul._blur
    ma, mb = blur(a), blur(b)
    va = blur(a * a) - ma * ma
    vb = blur(b * b) - mb * mb
    cov = blur(a * b) - ma * mb
    return np.mean(((2 * ma * mb + c1) * (2 * cov + c2))
                   / ((ma * ma + mb * mb + c1) * (va + vb + c2)), -1)


def score(seq, upscale, kind, seed, static, warm=WARM):
    """{region: (PSNR, SSIM, scintillement)} ; region « tout » comprise."""
    keys = ("tout", "fond", "anime", "objets", "hud")
    err = {k: [] for k in keys}
    sim = {k: [] for k in keys}
    fli = {k: [] for k in keys}
    prev = prev_gt = None
    for f, (img, j, gt) in enumerate(seq):
        out = np.clip(upscale(img, j), 0.0, 1.0)
        if f >= warm:
            masks = regions(kind, seed, static, f)
            masks["tout"] = np.ones(gt.shape[:2], bool)
            smap = ssim_map(out, gt)
            d = (np.abs((out - prev) - (gt - prev_gt))
                 if prev is not None else None)
            for k, m in masks.items():
                if m.any():
                    err[k].append(np.mean((out[m] - gt[m]) ** 2))
                    sim[k].append(smap[m].mean())
                    if d is not None:
                        fli[k].append(d[m].mean())
        prev, prev_gt = out, gt
    return {k: (10.0 * np.log10(1.0 / np.mean(v)), float(np.mean(sim[k])),
                float(np.mean(fli[k])) if fli[k] else 0.0)
            for k, v in err.items() if v}


def run(network, ratios=(2, 3), scenes=SCENES, log=print):
    """Toutes les mesures ; renvoie la liste des lignes (dict)."""
    rows = []

    def record(name, ratio, level, method, r):
        pair = lambda k: [float(x) for x in r.get(k, (0.0, 0.0, 0.0))[:2]]
        row = {"scene": name, "ratio": ratio, "niveau": str(level),
               "methode": method, "psnr": float(r["tout"][0]),
               "ssim": float(r["tout"][1]), "scint": float(r["tout"][2]),
               "fond": pair("fond"), "objets": pair("objets"),
               "hud": pair("hud"), "anime": pair("anime")}
        rows.append(row)
        log("  %-13s x%d niveau %-7s %-15s PSNR %.2f  SSIM %.3f  "
            "scint. %.4f" % (name, ratio, row["niveau"], method, row["psnr"],
                             row["ssim"], row["scint"]))

    def usr(rsize, period, net):
        up = universel.UniversalUpscaler(rsize, DISPLAY, network=net,
                                         period=period)
        return lambda img, j: up.dispatch(img, j)

    for ratio in ratios:
        rsize = RENDER[ratio]
        for kind, seed, static in scenes:
            if ratio == 3 and kind == "brut":
                continue
            name = "%s%d%s" % (kind, seed, "-fixe" if static else "")
            key = dict(kind=kind, seed=seed, static=static)
            s1 = sequence(kind, seed, static, rsize)
            record(name, ratio, 0, "bilineaire", score(
                s1, lambda i, j: evaluate.bilinear_upscale(i, DISPLAY), **key))
            record(name, ratio, 0, "lanczos", score(
                s1, lambda i, j: universel.lanczos_upscale(i, DISPLAY), **key))
            record(name, ratio, 0, "spatial (FSR1)", score(
                s1, lambda i, j: universel.spatial_upscale(i, DISPLAY), **key))
            record(name, ratio, 1, "USR-U regles",
                   score(s1, usr(rsize, 0, None), **key))
            if network is not None:
                record(name, ratio, 1, "USR-U IA",
                       score(s1, usr(rsize, 0, network), **key))
            for lod in (-1.0, 0.0):
                if kind == "brut" and lod == 0.0:
                    continue   # scene sans textures filtrees : lod sans effet
                s2 = sequence(kind, seed, static, rsize, "grille", lod)
                level = "2" if lod == 0.0 else "2 lod-1"
                period = ratio * ratio
                record(name, ratio, level, "USR-U regles",
                       score(s2, usr(rsize, period, None), **key))
                if network is not None:
                    record(name, ratio, level, "USR-U IA",
                           score(s2, usr(rsize, period, network), **key))
    return rows


def save(rows, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=1)
