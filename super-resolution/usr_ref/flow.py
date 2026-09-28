"""Estimation du mouvement a partir des seules images (mode Universel).

Quand le jeu ne fournit pas de vecteurs de mouvement (emulateur, capture),
USR les estime en comparant l'image courante a la precedente : pour chaque
pixel, ou etait ce petit motif a l'image d'avant ?

On estime directement le mouvement de la SCENE ``m`` (pixels de rendu),
pas celui de l'image : si l'emulateur decale l'echantillonnage d'une image
a l'autre (jitter connu J), le contenu du pixel p se trouvait a l'image
precedente en ``p + f`` avec ``f = (J_t - J_t-1) - m``. Travailler en ``m``
rend les candidats comparables d'une image a l'autre (le mouvement de la
camera est lisse, le jitter ne l'est pas).

Algorithme (identique, operation par operation, a shaders/usr_flow_*.hlsl) :

1. luminance entiere (R + 2 G + B sur 8 bits), puis flottante ; pyramide
   2x2 ;
2. du niveau le plus grossier au plus fin, on essaie des candidats et on
   garde celui dont le motif 5x5 ressemble le plus (somme des differences
   absolues, image precedente interpolee bilineairement), plus une legere
   penalite d'ecart au mouvement « attendu » (proportionnelle au contraste
   local) qui departage les zones sans texture ; les couts sont compares a
   une resolution fixe (meme choix sur tous les GPU) :
   * niveau grossier : grille entiere +-4 autour de zero, et +-1 autour du
     mouvement de l'image precedente (predicteur temporel) ;
   * niveaux fins : mouvement du niveau parent (et de ses 4 voisins), zero,
     predicteur temporel ; au niveau fin, aussi « f = 0 » (pixel fixe a
     l'ecran malgre le jitter : HUD) ;
3. affinage sous-pixel par une iteration de Lucas-Kanade (moindres carres
   sur le motif, x et y ensemble) ;
4. filtre median vectoriel 3x3 (elimine les vecteurs aberrants) ;
5. au niveau fin :
   * confiance : residu du meilleur appariement rapporte au contraste local
     (0 = fiable, 1 = zone decouverte, changement sans mouvement...) ;
   * pixels identiques a l'image precedente (test exact) : fixes a l'ecran
     -> f = 0 et « non soumis au jitter » (HUD dessine sans jitter) ;
   * pixels identiques a l'image de MEME phase de jitter (P images plus
     tot) : scene immobile a cet endroit -> m = 0 exactement.
"""

import numpy as np

PATCH_R = 2                 # motif 5x5
COST_SCALE = 4096.0         # resolution des couts compares (luminance)
MEDIAN_SCALE = 1024.0       # resolution des distances de la mediane (px)
COARSE_RADIUS = 4           # recherche entiere au niveau grossier
MIN_COARSE_SIDE = 24        # le niveau le plus grossier garde >= 24 px
MAX_LEVELS = 6
LAMBDA = 0.02               # penalite d'ecart au mouvement attendu
CONTRAST_FLOOR = 0.004      # plancher de contraste (luminance, par tap)
LK_MAX_STEP = 0.75          # deplacement maximal de l'affinage (pixels)
LK_COND = 0.01              # rejet des systemes mal conditionnes (ouverture)
CONF_FLOOR = 0.012          # plancher de contraste de la confiance
CONF_T0 = 0.6               # residu relatif : debut de rejet
CONF_T1 = 1.6               # residu relatif : rejet total
MAX_PERIOD = 16             # au-dela, pas de test « meme phase »

F32 = np.float32


# --------------------------------------------------------------------------
# Pyramide
# --------------------------------------------------------------------------

def luma_int(img):
    """Luminance YCoCg entiere : R + 2 G + B sur les valeurs 8 bits (0..1020).

    Calculee a partir des canaux ramenes a 8 bits (arrondi), elle est
    exactement la meme sur tous les GPU, quel que soit le format d'entree :
    le flot ne depend pas de l'arrondi (a un ulp pres) de la conversion
    UNORM -> flottant du materiel."""
    k = np.floor(np.clip(np.asarray(img, F32), 0.0, 1.0) * F32(255.0)
                 + F32(0.5))
    return (k[..., 0] + F32(2.0) * k[..., 1] + k[..., 2]).astype(F32)


def luma(img):
    """Luminance flottante [0, 1] du flot (luma_int / 1020)."""
    return (luma_int(img) * F32(1.0 / 1020.0)).astype(F32)


def luma16(img):
    """Luminance entiere : sert aux tests d'egalite exacte."""
    return luma_int(img).astype(np.int32)


def quantize_cost(cost, scale):
    """Les couts sont compares a une resolution fixe : deux candidats plus
    proches que 1/scale sont departages par l'ordre de la liste, et non par
    le bruit d'arrondi du GPU (resultat identique partout)."""
    return np.floor(cost * F32(scale) + F32(0.5)).astype(F32)


def down2(a):
    """Reduction 2x2 (moyenne), bords repliques."""
    h, w = a.shape
    ys = np.arange((h + 1) // 2)
    xs = np.arange((w + 1) // 2)
    y0 = np.minimum(2 * ys, h - 1)[:, None]
    y1 = np.minimum(2 * ys + 1, h - 1)[:, None]
    x0 = np.minimum(2 * xs, w - 1)[None, :]
    x1 = np.minimum(2 * xs + 1, w - 1)[None, :]
    return ((a[y0, x0] + a[y0, x1] + a[y1, x0] + a[y1, x1])
            * F32(0.25)).astype(F32)


def level_count(w, h):
    n = 1
    while min(w, h) >> n >= MIN_COARSE_SIDE and n < MAX_LEVELS:
        n += 1
    return n


def pyramid(lum, levels):
    pyr = [lum.astype(F32)]
    for _ in range(levels - 1):
        pyr.append(down2(pyr[-1]))
    return pyr


def gradient(a):
    """Differences centrees (bords repliques) : (gx, gy)."""
    h, w = a.shape
    xs = np.arange(w)
    ys = np.arange(h)
    gx = (a[:, np.minimum(xs + 1, w - 1)] - a[:, np.maximum(xs - 1, 0)]) \
        * F32(0.5)
    gy = (a[np.minimum(ys + 1, h - 1), :] - a[np.maximum(ys - 1, 0), :]) \
        * F32(0.5)
    return gx.astype(F32), gy.astype(F32)


# --------------------------------------------------------------------------
# Briques (une par fonction du shader)
# --------------------------------------------------------------------------

def bilinear(img, x, y):
    """Interpolation bilineaire aux coordonnees pixel (x, y), bornees au
    bord -- ecrite a la main dans le shader (pas l'unite de filtrage, dont
    la precision varie d'un GPU a l'autre)."""
    h, w = img.shape
    x = np.clip(x, F32(0.0), F32(w - 1))
    y = np.clip(y, F32(0.0), F32(h - 1))
    x0 = np.floor(x)
    y0 = np.floor(y)
    ax = (x - x0).astype(F32)
    ay = (y - y0).astype(F32)
    ix0 = x0.astype(np.int64)
    iy0 = y0.astype(np.int64)
    ix1 = np.minimum(ix0 + 1, w - 1)
    iy1 = np.minimum(iy0 + 1, h - 1)
    top = img[iy0, ix0] + (img[iy0, ix1] - img[iy0, ix0]) * ax
    bot = img[iy1, ix0] + (img[iy1, ix1] - img[iy1, ix0]) * ax
    return (top + (bot - top) * ay).astype(F32)


class _Grid:
    def __init__(self, h, w):
        ys, xs = np.mgrid[0:h, 0:w]
        self.h, self.w = h, w
        self.ys = ys
        self.xs = xs
        self.fy = ys.astype(F32)
        self.fx = xs.astype(F32)

    def tap(self, img, ox, oy):
        return img[np.clip(self.ys + oy, 0, self.h - 1),
                   np.clip(self.xs + ox, 0, self.w - 1)]


def patch_sad(cur, prev, g, fx, fy):
    """SAD 5x5 entre cur autour de p et prev autour de p + f (bilineaire)."""
    acc = np.zeros((g.h, g.w), F32)
    for oy in range(-PATCH_R, PATCH_R + 1):
        for ox in range(-PATCH_R, PATCH_R + 1):
            c = g.tap(cur, ox, oy)
            p = bilinear(prev, g.fx + F32(ox) + fx, g.fy + F32(oy) + fy)
            acc = acc + np.abs(c - p)
    return acc


def contrast(cur, g):
    """Somme des ecarts a la moyenne sur le motif 5x5 (25 x ecart moyen)."""
    taps = [g.tap(cur, ox, oy) for oy in range(-PATCH_R, PATCH_R + 1)
            for ox in range(-PATCH_R, PATCH_R + 1)]
    total = np.zeros((g.h, g.w), F32)
    for t in taps:
        total = total + t
    mean = total * F32(1.0 / 25.0)
    acc = np.zeros((g.h, g.w), F32)
    for t in taps:
        acc = acc + np.abs(t - mean)
    return acc


def exact_same(cur16, old16, g):
    """Vrai si le motif 5x5 est identique (entiers) dans les deux images."""
    diff = np.zeros((g.h, g.w), np.int32)
    for oy in range(-PATCH_R, PATCH_R + 1):
        for ox in range(-PATCH_R, PATCH_R + 1):
            diff = diff + np.abs(g.tap(cur16, ox, oy) - g.tap(old16, ox, oy))
    return diff == 0


def select(cur, prev, g, candidates, prior, djx, djy, weight):
    """Meilleur candidat (mx, my) : SAD + LAMBDA * contraste * |m - prior|.

    Ordre fixe, remplacement seulement si strictement meilleur."""
    best = None
    bx = by = None
    for cx, cy in candidates:
        cost = quantize_cost(patch_sad(cur, prev, g, djx - cx, djy - cy)
                             + weight * (np.abs(cx - prior[0])
                                         + np.abs(cy - prior[1])),
                             COST_SCALE)
        if best is None:
            best, bx, by = cost, cx.astype(F32), cy.astype(F32)
        else:
            better = cost < best
            best = np.where(better, cost, best)
            bx = np.where(better, cx, bx).astype(F32)
            by = np.where(better, cy, by).astype(F32)
    return bx, by


def lucas_kanade(cur, prev, grad, g, fx, fy):
    """Une iteration de Gauss-Newton sur le motif 5x5 (deplacement d'image)."""
    gxp, gyp = grad
    a11 = np.zeros((g.h, g.w), F32)
    a12 = np.zeros((g.h, g.w), F32)
    a22 = np.zeros((g.h, g.w), F32)
    b1 = np.zeros((g.h, g.w), F32)
    b2 = np.zeros((g.h, g.w), F32)
    for oy in range(-PATCH_R, PATCH_R + 1):
        for ox in range(-PATCH_R, PATCH_R + 1):
            x = g.fx + F32(ox) + fx
            y = g.fy + F32(oy) + fy
            gx = bilinear(gxp, x, y)
            gy = bilinear(gyp, x, y)
            it = g.tap(cur, ox, oy) - bilinear(prev, x, y)
            a11 = a11 + gx * gx
            a12 = a12 + gx * gy
            a22 = a22 + gy * gy
            b1 = b1 + gx * it
            b2 = b2 + gy * it
    det = a11 * a22 - a12 * a12
    tr = a11 + a22
    ok = det > F32(LK_COND) * tr * tr + F32(1e-10)
    inv = F32(1.0) / np.where(ok, det, F32(1.0))
    dx = np.where(ok, (a22 * b1 - a12 * b2) * inv, F32(0.0))
    dy = np.where(ok, (a11 * b2 - a12 * b1) * inv, F32(0.0))
    step = F32(LK_MAX_STEP)
    return ((fx + np.clip(dx, -step, step)).astype(F32),
            (fy + np.clip(dy, -step, step)).astype(F32))


def vector_median(mx, my):
    """Mediane vectorielle 3x3 : le voisin le plus proche (L1) des autres."""
    h, w = mx.shape
    g = _Grid(h, w)
    cand = [(g.tap(mx, ox, oy), g.tap(my, ox, oy))
            for oy in (-1, 0, 1) for ox in (-1, 0, 1)]
    best = None
    bx = by = None
    for cx, cy in cand:
        s = np.zeros((h, w), F32)
        for ox_, oy_ in cand:
            s = s + np.abs(cx - ox_) + np.abs(cy - oy_)
        s = quantize_cost(s, MEDIAN_SCALE)
        if best is None:
            best, bx, by = s, cx, cy
        else:
            better = s < best
            best = np.where(better, s, best)
            bx = np.where(better, cx, bx)
            by = np.where(better, cy, by)
    return bx.astype(F32), by.astype(F32)


def _parent(mx, my, g, ox=0, oy=0):
    ph, pw = mx.shape
    py = np.clip(g.ys // 2 + oy, 0, ph - 1)
    px = np.clip(g.xs // 2 + ox, 0, pw - 1)
    return F32(2.0) * mx[py, px], F32(2.0) * my[py, px]


def _temporal(prev_m, g, level):
    """Mouvement final de l'image precedente, ramene au niveau ``level``
    (echantillon au centre du bloc correspondant)."""
    mx, my = prev_m
    h, w = mx.shape
    s = 1 << level
    half = s // 2
    y = np.minimum(g.ys * s + half, h - 1)
    x = np.minimum(g.xs * s + half, w - 1)
    k = F32(1.0 / s)
    return mx[y, x] * k, my[y, x] * k


# --------------------------------------------------------------------------
# Estimateur complet (etat d'une image a l'autre)
# --------------------------------------------------------------------------

class FlowEstimator:
    """Mouvement de scene pour chaque pixel de rendu, image apres image.

    ``period`` : periode de la sequence de jitter (0 = pas de jitter ou
    sequence non periodique) ; sert au test exact « meme phase ».
    ``__call__`` renvoie un dict : ``motion`` (h, w, 2) en pixels de rendu
    (le point vu au pixel p etait, dans la scene, en p - m a l'image
    precedente), ``conf`` (0 fiable .. 1 a rejeter), ``jflag`` (1 si le
    pixel suit le jitter, 0 pour un HUD fixe), ``static`` (1 si un test
    exact a fixe le mouvement)."""

    def __init__(self, render_size, period=0):
        self.w, self.h = render_size
        self.levels = level_count(self.w, self.h)
        self.period = int(period) if 1 < int(period) <= MAX_PERIOD else 0
        self.prev_pyr = None
        self.prev_grad = None
        self.prev_jitter = None
        self.prev_m = None
        self.ring = []          # luminances 16 bits des images precedentes

    def reset(self):
        self.prev_pyr = self.prev_grad = self.prev_jitter = None
        self.prev_m = None
        self.ring = []

    def __call__(self, image, jitter=(0.0, 0.0)):
        lum = luma(image)
        l16 = luma16(image)
        pyr = pyramid(lum, self.levels)
        grads = [gradient(level) for level in pyr]
        h, w = self.h, self.w
        g0 = _Grid(h, w)
        zero = np.zeros((h, w), F32)
        if self.prev_pyr is None:
            out = {"motion": np.stack([zero, zero], -1),
                   "conf": np.ones((h, w), F32),
                   "jflag": np.ones((h, w), F32),
                   "static": np.zeros((h, w), F32)}
            self._push(pyr, grads, jitter, (zero, zero), l16)
            return out

        djx = F32(jitter[0] - self.prev_jitter[0])
        djy = F32(jitter[1] - self.prev_jitter[1])
        mx = my = None
        top = self.levels - 1
        for lvl in range(top, -1, -1):
            cur, prev = pyr[lvl], self.prev_pyr[lvl]
            lh, lw = cur.shape
            g = _Grid(lh, lw)
            s = F32(1.0 / (1 << lvl))
            jx, jy = djx * s, djy * s
            weight = F32(LAMBDA) * (contrast(cur, g)
                                    + F32(25.0 * CONTRAST_FLOOR))
            tpx, tpy = _temporal(self.prev_m, g, lvl)
            full = lambda v: np.full((lh, lw), v, F32)  # noqa: E731
            if mx is None:
                cands = [(full(ox), full(oy))
                         for oy in range(-COARSE_RADIUS, COARSE_RADIUS + 1)
                         for ox in range(-COARSE_RADIUS, COARSE_RADIUS + 1)]
                cands += [(tpx + F32(ox), tpy + F32(oy))
                          for oy in (-1, 0, 1) for ox in (-1, 0, 1)]
                prior = (full(0.0), full(0.0))
            else:
                prior = _parent(mx, my, g)
                cands = [prior]
                if lvl > 0:
                    cands += [_parent(mx, my, g, ox, oy)
                              for ox, oy in ((-1, 0), (1, 0), (0, -1),
                                             (0, 1))]
                cands += [(full(0.0), full(0.0)), (tpx, tpy)]
                if lvl == 0:
                    cands.append((full(djx), full(djy)))    # f = 0 (HUD)
            bx, by = select(cur, prev, g, cands, prior, jx, jy, weight)
            fx, fy = lucas_kanade(cur, prev, self.prev_grad[lvl], g,
                                  jx - bx, jy - by)
            mx, my = vector_median((jx - fx).astype(F32),
                                   (jy - fy).astype(F32))

        # confiance : residu relatif au contraste local
        res = patch_sad(pyr[0], self.prev_pyr[0], g0, djx - mx, djy - my)
        rel = res / (contrast(pyr[0], g0) + F32(25.0 * CONF_FLOOR))
        conf = np.clip((rel - F32(CONF_T0)) / F32(CONF_T1 - CONF_T0),
                       0.0, 1.0).astype(F32)
        jflag = np.ones((h, w), F32)
        static = np.zeros((h, w), F32)

        # pixel identique a l'image precedente : fixe a l'ecran (f = 0)
        same = exact_same(l16, self.ring[-1], g0)
        mx = np.where(same, djx, mx).astype(F32)
        my = np.where(same, djy, my).astype(F32)
        if djx != 0.0 or djy != 0.0:
            jflag = np.where(same, F32(0.0), jflag)
        # identique a l'image de meme phase : scene immobile (m = 0)
        if self.period and len(self.ring) >= self.period:
            same_p = exact_same(l16, self.ring[-self.period], g0) & ~same
            mx = np.where(same_p, F32(0.0), mx)
            my = np.where(same_p, F32(0.0), my)
            same = same | same_p
        conf = np.where(same, F32(0.0), conf)
        static = np.where(same, F32(1.0), static)

        out = {"motion": np.stack([mx, my], -1).astype(F32), "conf": conf,
               "jflag": jflag.astype(F32), "static": static.astype(F32)}
        self._push(pyr, grads, jitter, (mx, my), l16)
        return out

    def _push(self, pyr, grads, jitter, m, l16):
        self.prev_pyr = pyr
        self.prev_grad = grads
        self.prev_jitter = (float(jitter[0]), float(jitter[1]))
        self.prev_m = m
        self.ring.append(l16)
        keep = max(self.period, 1)
        if len(self.ring) > keep:
            self.ring = self.ring[-keep:]
