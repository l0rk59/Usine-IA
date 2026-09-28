"""Scenario « jeu emule » : exactement ce que Xenia peut donner a USR.

Dans un emulateur, l'upscaler ne voit que l'image finale du jeu :

* rendue a la resolution du jeu (souvent 1280x720), un echantillon au
  centre de chaque pixel -- pas de jitter, sauf si l'emulateur l'injecte
  lui-meme (niveau 2) ;
* avec le HUD deja dessine par-dessus (texte, barres, viseur : fixes) ;
* deja compressee pour l'ecran et quantifiee (8 bits) ;
* sans profondeur ni vecteurs de mouvement.

La verite terrain est le meme jeu rendu directement a la resolution
d'affichage avec 16 echantillons par pixel, HUD compris. Les mesures se
font dans l'espace de l'ecran, la ou l'oeil juge.
"""

import numpy as np

from .scene import Scene

# HUD : couleurs lineaires (HDR), composees avant la compression du jeu.
HUD_WHITE = np.array([3.0, 3.0, 2.6])
HUD_RED = np.array([2.2, 0.25, 0.2])
HUD_YELLOW = np.array([3.0, 2.4, 0.4])


def encode_display(linear):
    """Compression du « jeu » (Reinhard sur le max + gamma 2.2)."""
    c = np.maximum(linear, 0.0)
    y = c / (1.0 + np.max(c, axis=-1, keepdims=True))
    return np.power(np.clip(y, 0.0, 1.0), 1.0 / 2.2)


def quantize(img, bits=8):
    q = float((1 << bits) - 1)
    return (np.round(np.clip(img, 0.0, 1.0) * q) / q).astype(np.float32)


def _hash(ix, iy):
    h = (ix * 73856093) ^ (iy * 19349663)
    h = (h ^ (h >> 13)) * 1274126177
    return (h ^ (h >> 16)) & 0xFFFFFFFF


def hud(u, v, aspect):
    """Couverture et couleur du HUD au point (u, v) de l'ecran.

    Renvoie (masque booleen, couleur lineaire). Tailles en fraction de la
    hauteur d'ecran, comme un HUD 720p : traits de 1 a 3 pixels 720p.
    """
    x = u * aspect   # unites : hauteur d'ecran
    y = v
    col = np.zeros(u.shape + (3,))
    mask = np.zeros(u.shape, bool)

    # barre de vie : cadre fin + remplissage
    bx0, bx1, by0, by1 = 0.06, 0.52, 0.905, 0.94
    inside = (x > bx0) & (x < bx1) & (y > by0) & (y < by1)
    border = inside & ((x < bx0 + 0.003) | (x > bx1 - 0.003)
                       | (y < by0 + 0.003) | (y > by1 - 0.003))
    fill = inside & ~border & (x < bx0 + 0.72 * (bx1 - bx0))
    mask |= border | fill
    col = np.where(border[..., None], HUD_WHITE, col)
    col = np.where(fill[..., None], HUD_RED, col)

    # texte « matriciel » 5x7 en haut a gauche (glyphes pseudo-aleatoires)
    tx0, ty0, cw, ch = 0.06, 0.05, 0.022, 0.032
    cx = np.floor((x - tx0) / cw).astype(np.int64)
    cy = np.floor((y - ty0) / ch).astype(np.int64)
    in_text = (cx >= 0) & (cx < 22) & (cy >= 0) & (cy < 2)
    gx = np.floor(((x - tx0) / cw - cx) * 6.0).astype(np.int64)  # 5 + espace
    gy = np.floor(((y - ty0) / ch - cy) * 8.0).astype(np.int64)  # 7 + espace
    bit = (_hash(cx + 101 * cy, gx + 7 * gy) >> 7) & 1
    on = in_text & (gx < 5) & (gy < 7) & (bit == 1)
    mask |= on
    col = np.where(on[..., None], HUD_WHITE, col)

    # viseur au centre : traits de 1,5 pixel 720p
    dx = x - 0.5 * aspect
    dy = y - 0.5
    arm = ((np.abs(dx) < 0.0011) & (np.abs(dy) > 0.012) & (np.abs(dy) < 0.04)
           ) | ((np.abs(dy) < 0.0011) & (np.abs(dx) > 0.012)
                & (np.abs(dx) < 0.04))
    mask |= arm
    col = np.where(arm[..., None], HUD_YELLOW, col)
    return mask, col


class EmulatedGame:
    """Un « jeu » tel que vu depuis l'emulateur."""

    def __init__(self, scene=None, with_hud=True, bits=8):
        self.scene = scene or Scene(seed=101)
        self.with_hud = with_hud
        self.bits = bits
        self._truth_cache = {}

    def _shade(self, t, u, v, footprint=None, hud_uv=None):
        if getattr(self.scene, "shade", None) and footprint is not None and \
                "footprint" in self.scene.shade.__code__.co_varnames:
            color, invz, motion = self.scene.shade(t, u, v, footprint)
        else:
            color, invz, motion = self.scene.shade(t, u, v)
        if self.with_hud:
            m, c = hud(*(hud_uv or (u, v)), self.scene.aspect)
            color = np.where(m[..., None], c, color).astype(np.float32)
            invz = np.where(m, 1.0, invz).astype(np.float32)    # tout devant
            motion = np.where(m[..., None], 0.0, motion).astype(np.float32)
        return color, invz, motion

    def frame(self, t, size, jitter=(0.0, 0.0), lod_bias=0.0,
              hud_jitter=True):
        """Image que le jeu envoie a l'ecran : 1 echantillon par pixel.

        ``lod_bias`` : biais de niveau de mip-map (log2) applique aux
        textures, comme un emulateur peut l'injecter (-1 = textures deux
        fois plus fines). ``hud_jitter=False`` : le jitter ne touche que la
        scene 3D, pas le HUD (ce que fait l'injection de jitter de Xenia,
        limitee aux dessins avec profondeur).

        Renvoie (image ecran quantifiee, 1/z vrai, mouvement vrai) ; les
        deux derniers ne servent qu'aux mesures (« oracle »)."""
        w, h = size
        ys, xs = np.mgrid[0:h, 0:w]
        u = (xs + 0.5 + jitter[0]) / w
        v = (ys + 0.5 + jitter[1]) / h
        color, invz, motion = self._shade(t, u, v,
                                          footprint=2.0 ** lod_bias / h,
                                          hud_uv=None if hud_jitter else (
                                              (xs + 0.5) / w, (ys + 0.5) / h))
        return quantize(encode_display(color), self.bits), invz, motion

    def truth(self, t, size, ss=4):
        key = (t, tuple(size), ss)
        if key in self._truth_cache:
            return self._truth_cache[key]
        w, h = size
        ys, xs = np.mgrid[0:h, 0:w]
        acc = np.zeros((h, w, 3))
        for j in range(ss):
            for i in range(ss):
                c, _, _ = self._shade(t, (xs + (i + 0.5) / ss) / w,
                                      (ys + (j + 0.5) / ss) / h,
                                      footprint=1.0 / (h * ss))
                acc += c
        out = encode_display(acc / (ss * ss)).astype(np.float32)
        self._truth_cache[key] = out
        return out


def psnr_display(a, b):
    mse = float(np.mean((np.asarray(a, np.float64) - b) ** 2))
    return 10.0 * np.log10(1.0 / max(mse, 1e-12))


def _blur(x, sigma=1.5, radius=5):
    """Flou gaussien separable (bords repliques), sur les deux premiers
    axes."""
    k = np.exp(-0.5 * (np.arange(-radius, radius + 1) / sigma) ** 2)
    k /= k.sum()
    h, w = x.shape[:2]
    pad = np.pad(x, ((radius, radius), (0, 0)) + ((0, 0),) * (x.ndim - 2),
                 mode="edge")
    acc = sum(k[i] * pad[i:i + h] for i in range(2 * radius + 1))
    pad = np.pad(acc, ((0, 0), (radius, radius)) + ((0, 0),) * (x.ndim - 2),
                 mode="edge")
    return sum(k[i] * pad[:, i:i + w] for i in range(2 * radius + 1))


def ssim_display(a, b):
    """SSIM (Wang et al. 2004 : fenetre gaussienne 11x11, sigma 1,5), moyen
    sur R, G, B. 1 = identique ; sensible a la structure plus qu'au PSNR."""
    a = np.asarray(a, np.float64)
    b = np.asarray(b, np.float64)
    c1, c2 = 0.01 ** 2, 0.03 ** 2
    ma, mb = _blur(a), _blur(b)
    va = _blur(a * a) - ma * ma
    vb = _blur(b * b) - mb * mb
    cov = _blur(a * b) - ma * mb
    s = ((2 * ma * mb + c1) * (2 * cov + c2)) / (
        (ma * ma + mb * mb + c1) * (va + vb + c2))
    return float(np.mean(s))
