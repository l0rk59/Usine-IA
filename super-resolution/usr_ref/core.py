"""Implementation de reference (NumPy) des trois passes de l'upscaler USR.

Chaque fonction reproduit, formule pour formule et dans le meme ordre, un
shader de ``shaders/``. C'est ce qui permet de mettre au point l'algorithme
sur n'importe quelle machine, puis de verifier que les shaders GPU donnent
le meme resultat (voir ``tests/test_parite_gpu.py``).

Conventions (identiques a la bibliotheque C++) :

* tableaux image en ``(hauteur, largeur, canaux)``, ligne 0 en haut ;
* uv dans [0, 1], centre du pixel ``i`` a ``(i + 0.5) / taille`` ;
* ``jitter`` en pixels de rendu : le pixel de rendu ``i`` contient la scene
  echantillonnee en ``(i + 0.5 + jitter) / taille_rendu`` ;
* ``motion`` en unites uv : ``uv_precedent = uv_courant - motion`` ;
* ``invz`` = 1 / profondeur lineaire (plus grand = plus proche).
  Le shader le calcule depuis la profondeur materielle : ``d * P0 + P1``.
"""

import numpy as np

# --- Constantes partagees avec shaders/usr_common.hlsli (a garder egales) ---
SIGMA_FRESH = 0.60          # noyau spatial (pixels de rendu) sans historique
SIGMA_SHARP_DISPLAY = 0.47  # noyau d'accumulation (pixels d'affichage)
KERNEL_COUNT = 3.0          # historique a partir duquel le noyau est etroit
DISOCC_T0 = 0.02            # ecart relatif de profondeur : debut de rejet
DISOCC_T1 = 0.06            # ecart relatif de profondeur : rejet total
SHARPEN_PEAK = 0.2          # force maximale de l'accentuation
EPS_SIGMA = 0.004           # plancher d'ecart-type pour les caracteristiques

DEFAULT_MAX_COUNT = 10.0
DEFAULT_CLIP_GAMMA = 1.25

FLAG_RESET = 1
FLAG_NETWORK = 2

N_FEATURES = 10


# --------------------------------------------------------------------------
# Espaces de couleur
# --------------------------------------------------------------------------

def tonemap(c):
    """Compression reversible : garde l'accumulation stable en HDR."""
    return c / (1.0 + np.max(c, axis=-1, keepdims=True))


def untonemap(y):
    return y / np.maximum(1.0 - np.max(y, axis=-1, keepdims=True), 1e-3)


def rgb_to_ycocg(c):
    r, g, b = c[..., 0], c[..., 1], c[..., 2]
    return np.stack([0.25 * r + 0.5 * g + 0.25 * b,
                     0.5 * r - 0.5 * b,
                     -0.25 * r + 0.5 * g - 0.25 * b], axis=-1)


def ycocg_to_rgb(y):
    t = y[..., 0] - y[..., 2]
    return np.stack([t + y[..., 1], y[..., 0] + y[..., 2], t - y[..., 1]],
                    axis=-1)


# --------------------------------------------------------------------------
# Stockage GPU emule : ce que les textures arrondissent
# --------------------------------------------------------------------------

def as_f16(x):
    return np.asarray(x, np.float32).astype(np.float16).astype(np.float32)


def as_unorm8(x):
    return np.round(np.clip(x, 0.0, 1.0) * 255.0).astype(np.float32) / 255.0


def _sat(x):
    return np.clip(x, 0.0, 1.0)


def _sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


# --------------------------------------------------------------------------
# Passe 1 : dilatation des vecteurs de mouvement + detection de desocclusion
# --------------------------------------------------------------------------

def prepare(invz, motion, prev_invz, jitter, reset):
    """Retourne (mouvement dilate, invz dilate, desocclusion).

    Le vecteur retenu pour chaque pixel est celui du voisin 3x3 le plus
    proche de la camera : les bords d'objets suivent l'objet, pas le fond.
    """
    h, w = invz.shape
    ys, xs = np.mgrid[0:h, 0:w]

    best = invz.astype(np.float32).copy()
    best_mv = motion.astype(np.float32).copy()
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dx == 0 and dy == 0:
                continue
            qy = np.clip(ys + dy, 0, h - 1)
            qx = np.clip(xs + dx, 0, w - 1)
            z = invz[qy, qx]
            closer = z > best
            best = np.where(closer, z, best)
            best_mv = np.where(closer[..., None], motion[qy, qx], best_mv)

    u = (xs + 0.5 + jitter[0]) / w
    v = (ys + 0.5 + jitter[1]) / h
    pu = u - best_mv[..., 0]
    pv = v - best_mv[..., 1]
    inside = (pu >= 0.0) & (pu <= 1.0) & (pv >= 0.0) & (pv <= 1.0)

    x0 = np.floor(pu * w - 0.5).astype(np.int64)
    y0 = np.floor(pv * h - 0.5).astype(np.int64)
    z_cur = 1.0 / np.maximum(best, 1e-8)
    closest = np.full(invz.shape, np.inf, np.float32)
    for oy in (0, 1):
        for ox in (0, 1):
            qx = np.clip(x0 + ox, 0, w - 1)
            qy = np.clip(y0 + oy, 0, h - 1)
            z_prev = 1.0 / np.maximum(prev_invz[qy, qx], 1e-8)
            # > 0 : la surface vue au meme endroit a l'image precedente etait
            # plus proche, donc elle cachait ce qu'on voit maintenant.
            closest = np.minimum(closest, (z_cur - z_prev) / z_cur)
    disocc = _sat((closest - DISOCC_T0) / (DISOCC_T1 - DISOCC_T0))
    disocc = np.where(inside & (not reset), disocc, 1.0)

    return (as_f16(best_mv), best.astype(np.float32),
            as_unorm8(disocc))


# --------------------------------------------------------------------------
# Passe 2 : reprojection, rectification, reseau, accumulation
# --------------------------------------------------------------------------

def _catmull_rom_weights(f):
    return (f * (-0.5 + f * (1.0 - 0.5 * f)),
            1.0 + f * f * (-2.5 + 1.5 * f),
            f * (0.5 + f * (2.0 - 1.5 * f)),
            f * f * (-0.5 + 0.5 * f))


def sample_catmull_rom(tex, u, v):
    h, w = tex.shape[:2]
    px = u * w - 0.5
    py = v * h - 0.5
    ix = np.floor(px)
    iy = np.floor(py)
    wx = _catmull_rom_weights(px - ix)
    wy = _catmull_rom_weights(py - iy)
    ix = ix.astype(np.int64)
    iy = iy.astype(np.int64)
    acc = np.zeros(u.shape + tex.shape[2:], np.float32)
    for j in range(4):
        qy = np.clip(iy + j - 1, 0, h - 1)
        for i in range(4):
            qx = np.clip(ix + i - 1, 0, w - 1)
            acc += tex[qy, qx] * (wx[i] * wy[j])[..., None]
    return acc


def sample_bilinear(tex, u, v):
    h, w = tex.shape[:2]
    px = u * w - 0.5
    py = v * h - 0.5
    ix = np.floor(px)
    iy = np.floor(py)
    fx = px - ix
    fy = py - iy
    if tex.ndim == 3:
        fx = fx[..., None]
        fy = fy[..., None]
    ix = ix.astype(np.int64)
    iy = iy.astype(np.int64)
    x0 = np.clip(ix, 0, w - 1)
    x1 = np.clip(ix + 1, 0, w - 1)
    y0 = np.clip(iy, 0, h - 1)
    y1 = np.clip(iy + 1, 0, h - 1)
    top = tex[y0, x0] * (1 - fx) + tex[y0, x1] * fx
    bot = tex[y1, x0] * (1 - fx) + tex[y1, x1] * fx
    return top * (1 - fy) + bot * fy


def clip_to_box(h, bmin, bmax):
    """Ramene h dans la boite [bmin, bmax] le long du rayon vers son centre."""
    center = 0.5 * (bmin + bmax)
    extent = 0.5 * (bmax - bmin) + 1e-5
    offset = h - center
    ratio = np.max(np.abs(offset) / extent, axis=-1, keepdims=True)
    return np.where(ratio > 1.0, center + offset / np.maximum(ratio, 1.0), h)


def accumulate(color, dilated_mv, disocc, history, jitter, display_size,
               reset=False, exposure=1.0, max_count=DEFAULT_MAX_COUNT,
               clip_gamma=DEFAULT_CLIP_GAMMA, network=None,
               return_internals=False):
    """Produit la nouvelle image d'historique (RGB compresse + confiance).

    ``history`` est le tableau (H, W, 4) de l'image precedente, ou ``None``.
    """
    rh, rw = color.shape[:2]
    dw, dh = display_size
    oy, ox = np.mgrid[0:dh, 0:dw]
    u = (ox + 0.5) / dw
    v = (oy + 0.5) / dh
    rpx = u * rw
    rpy = v * rh
    rix = np.clip(np.floor(rpx).astype(np.int64), 0, rw - 1)
    riy = np.clip(np.floor(rpy).astype(np.int64), 0, rh - 1)
    mv = dilated_mv[riy, rix]
    dis = disocc[riy, rix]
    pu = u - mv[..., 0]
    pv = v - mv[..., 1]
    valid = ((pu >= 0.0) & (pu <= 1.0) & (pv >= 0.0) & (pv <= 1.0)
             & (not reset) & (history is not None))

    if history is not None:
        h_raw = np.maximum(sample_catmull_rom(history[..., :3], pu, pv), 0.0)
        count = sample_bilinear(history[..., 3], pu, pv)
    else:
        h_raw = np.zeros((dh, dw, 3), np.float32)
        count = np.zeros((dh, dw), np.float32)
    count_prev = np.where(valid, count * (1.0 - dis), 0.0)

    sigma_sharp = SIGMA_SHARP_DISPLAY * rw / dw
    sigma = SIGMA_FRESH + (sigma_sharp - SIGMA_FRESH) * _sat(
        count_prev / KERNEL_COUNT)
    inv2s2 = 1.0 / (2.0 * sigma * sigma)
    inv2s2_sharp = 1.0 / (2.0 * sigma_sharp * sigma_sharp)

    nsx = np.floor(rpx - jitter[0]).astype(np.int64)
    nsy = np.floor(rpy - jitter[1]).astype(np.int64)
    sum_w = np.zeros((dh, dw), np.float32)
    cw = np.zeros((dh, dw), np.float32)
    sum_c = np.zeros((dh, dw, 3), np.float32)
    m1 = np.zeros((dh, dw, 3), np.float32)
    m2 = np.zeros((dh, dw, 3), np.float32)
    mn = np.full((dh, dw, 3), np.inf, np.float32)
    mx = np.full((dh, dw, 3), -np.inf, np.float32)
    for dy in (-1, 0, 1):
        qy = np.clip(nsy + dy, 0, rh - 1)
        for dx in (-1, 0, 1):
            qx = np.clip(nsx + dx, 0, rw - 1)
            c = rgb_to_ycocg(tonemap(color[qy, qx] * exposure))
            ddx = qx + 0.5 + jitter[0] - rpx
            ddy = qy + 0.5 + jitter[1] - rpy
            d2 = ddx * ddx + ddy * ddy
            wgt = np.exp(-d2 * inv2s2)
            cw += np.exp(-d2 * inv2s2_sharp)
            sum_w += wgt
            sum_c += c * wgt[..., None]
            m1 += c
            m2 += c * c
            mn = np.minimum(mn, c)
            mx = np.maximum(mx, c)
    # Le poids d'accumulation vient toujours du noyau etroit : une image
    # floue (noyau large, pixel sans historique) ne doit pas peser lourd
    # dans la moyenne une fois que les images nettes arrivent.
    cur = sum_c / np.maximum(sum_w, 1e-6)[..., None]
    mean = m1 / 9.0
    std = np.sqrt(np.maximum(m2 / 9.0 - mean * mean, 0.0))

    hy = rgb_to_ycocg(h_raw)
    bmin = np.maximum(mean - clip_gamma * std, mn)
    bmax = np.minimum(mean + clip_gamma * std, mx)
    h_clip = clip_to_box(hy, bmin, bmax)

    alpha_heur = np.where(valid, cw / (count_prev + cw), 1.0)
    feats = None
    if network is not None:
        feats = features(alpha_heur, hy, h_clip, mean, std, cur, dis, mv,
                         cw, count_prev, pu, pv, (dw, dh), max_count)
        out = network.forward(feats.reshape(-1, N_FEATURES)).reshape(
            dh, dw, 2)
        a = np.clip(alpha_heur, 1e-4, 1.0 - 1e-4)
        alpha = _sigmoid(np.log(a / (1.0 - a)) + out[..., 0])
        beta = _sigmoid(out[..., 1])
        alpha = np.where(valid, alpha, 1.0)
        hist = h_clip + (hy - h_clip) * beta[..., None]
    else:
        alpha = alpha_heur
        beta = np.zeros_like(alpha)
        hist = h_clip

    res = hist + (cur - hist) * alpha[..., None]
    new_count = np.where(
        valid,
        np.minimum(np.minimum(count_prev + cw, cw / np.maximum(alpha, 1e-4)),
                   max_count),
        np.minimum(cw, max_count))
    history_new = np.concatenate(
        [np.maximum(ycocg_to_rgb(res), 0.0), new_count[..., None]], axis=-1)
    history_new = as_f16(history_new)

    if not return_internals:
        return history_new
    if feats is None:
        feats = features(alpha_heur, hy, h_clip, mean, std, cur, dis, mv,
                         cw, count_prev, pu, pv, (dw, dh), max_count)
    return history_new, {
        "valid": valid, "cur": ycocg_to_rgb(cur), "h_raw": h_raw,
        "h_clip": ycocg_to_rgb(h_clip), "alpha_heur": alpha_heur,
        "alpha": alpha, "beta": beta, "features": feats, "puv": (pu, pv),
    }


def features(alpha_heur, hy, h_clip, mean, std, cur, dis, mv, cw,
             count_prev, pu, pv, display_size, max_count):
    """Les 10 entrees du reseau, dans l'ordre de usr_network.hlsli."""
    dw, dh = display_size
    s_y = std[..., 0] + EPS_SIGMA
    s_len = np.sqrt(np.sum(std * std, axis=-1)) + EPS_SIGMA
    clip_len = np.sqrt(np.sum((hy - h_clip) ** 2, axis=-1))
    mvx = mv[..., 0] * dw
    mvy = mv[..., 1] * dh
    fx = pu * dw - 0.5
    fy = pv * dh - 0.5
    fx = fx - np.floor(fx)
    fy = fy - np.floor(fy)
    return np.stack([
        alpha_heur,
        np.minimum(np.abs(hy[..., 0] - mean[..., 0]) / s_y, 8.0),
        np.minimum(clip_len / s_len, 8.0),
        np.minimum(std[..., 0] / (mean[..., 0] + 0.02), 4.0),
        dis,
        np.log2(1.0 + np.sqrt(mvx * mvx + mvy * mvy)),
        np.minimum(cw, 4.0),
        count_prev / max_count,
        np.minimum(np.abs(cur[..., 0] - mean[..., 0]) / s_y, 8.0),
        4.0 * fx * (1.0 - fx) + 4.0 * fy * (1.0 - fy),
    ], axis=-1).astype(np.float32)


# --------------------------------------------------------------------------
# Passe 3 : accentuation adaptative au contraste + retour en lineaire
# --------------------------------------------------------------------------

def sharpen(history_new, sharpness=0.0, exposure=1.0):
    c = history_new[..., :3]
    if sharpness > 0.0:
        h, w = c.shape[:2]
        ys, xs = np.mgrid[0:h, 0:w]
        n = c[np.clip(ys - 1, 0, h - 1), xs]
        s = c[np.clip(ys + 1, 0, h - 1), xs]
        e = c[ys, np.clip(xs + 1, 0, w - 1)]
        wv = c[ys, np.clip(xs - 1, 0, w - 1)]
        mn = np.minimum(np.minimum(np.minimum(c, n), np.minimum(s, e)), wv)
        mx = np.maximum(np.maximum(np.maximum(c, n), np.maximum(s, e)), wv)
        amp = _sat(np.minimum(mn, 1.0 - mx) / np.maximum(mx, 1e-4))
        lobe = -SHARPEN_PEAK * sharpness * np.sqrt(amp)
        r = (c + lobe * (n + s + e + wv)) / (1.0 + 4.0 * lobe)
        c = np.clip(r, mn, mx)
    return as_f16(untonemap(c) / exposure)


# --------------------------------------------------------------------------
# Aides cote hote (miroir de include/usr/usr.h)
# --------------------------------------------------------------------------

QUALITY_MODES = {
    "natif": 1.0,
    "qualite": 1.5,
    "equilibre": 1.7,
    "performance": 2.0,
    "ultra": 3.0,
}


def render_size(display_size, mode):
    ratio = QUALITY_MODES[mode]
    return (max(1, int(round(display_size[0] / ratio))),
            max(1, int(round(display_size[1] / ratio))))


def halton(index, base):
    f, r = 1.0, 0.0
    while index > 0:
        f /= base
        r += f * (index % base)
        index //= base
    return r


def jitter_phase_count(render_w, display_w):
    ratio = display_w / render_w
    return max(8, int(np.ceil(8.0 * ratio * ratio)))


def jitter_offset(frame, phase_count):
    k = frame % phase_count + 1
    return (halton(k, 2) - 0.5, halton(k, 3) - 0.5)


class Upscaler:
    """Etat persistant d'une instance, comme usr::Context en C++."""

    def __init__(self, render_size, display_size, network=None,
                 max_count=DEFAULT_MAX_COUNT, clip_gamma=DEFAULT_CLIP_GAMMA):
        self.render_size = render_size
        self.display_size = display_size
        self.network = network
        self.max_count = max_count
        self.clip_gamma = clip_gamma
        self.history = None
        self.prev_invz = None

    def dispatch(self, color, invz, motion, jitter, reset=False,
                 sharpness=0.0, exposure=1.0, return_internals=False):
        reset = reset or self.history is None
        prev = self.prev_invz if self.prev_invz is not None else invz
        dmv, dinvz, dis = prepare(invz, motion, prev, jitter, reset)
        result = accumulate(color, dmv, dis, self.history, jitter,
                            self.display_size, reset=reset,
                            exposure=exposure, max_count=self.max_count,
                            clip_gamma=self.clip_gamma,
                            network=self.network,
                            return_internals=return_internals)
        if return_internals:
            self.history, internals = result
        else:
            self.history, internals = result, None
        self.prev_invz = dinvz
        out = sharpen(self.history, sharpness, exposure)
        return (out, internals) if return_internals else out
