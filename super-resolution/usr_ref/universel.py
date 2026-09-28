"""USR Universel : USR sans profondeur ni vecteurs de mouvement.

Pour les images dont on ne connait que les pixels (emulateur, capture).
C'est un algorithme a part entiere, pas USR avec des vecteurs estimes : sans
jitter garanti ni vecteurs exacts, l'accumulation de USR (qui reconstruit
chaque pixel a partir de l'echantillon le plus proche) donne une image en
escalier. Ici on accumule par retro-projection du residu :

* l'historique predit ce que l'image courante aurait du montrer aux
  positions exactes de ses echantillons (passe « residu ») ;
* seule l'ERREUR de cette prediction (le residu) est interpolee et ajoutee
  a l'historique. Sans information nouvelle (image fixe, sans jitter), le
  residu est nul et l'image reste celle d'un bon agrandissement spatial ;
  des qu'un mouvement ou un jitter apporte des echantillons a de nouvelles
  positions, les details s'accumulent (super-resolution) ;
* la ou la prediction echoue (zone decouverte, ecran anime, mouvement mal
  estime), la « reactivite » ramene le pixel vers l'image fraiche. Le petit
  reseau de neurones corrige deux decisions par pixel : cette reactivite et
  le gain d'accumulation (sorties 0 et 1).

Mouvement : estime par ``flow`` ; ``motion_source='oracle'`` utilise le vrai
mouvement (mesures seulement).

Jitter (niveau 2, injecte par l'emulateur) : pour un rapport entier, une
grille ordonnee (2x2, 3x3) donne a chaque pixel d'affichage un echantillon
exactement en son centre toutes les n*n images ; sinon Halton.

Espace de travail : YCoCg de l'image telle que le jeu l'affiche (deja
compressee, [0, 1]) ; pas de compression supplementaire.

Egalement ici, pour les comparaisons : un agrandissement spatial de type
FSR 1 (Lanczos-2 avec anti-rebond, puis accentuation RCAS), l'etat de l'art
sans historique -- celui que Xenia propose deja.

Chaque etape a son jumeau dans shaders/usr_u_*.hlsl (meme ordre des
operations, flottants 32 bits).
"""

import numpy as np

from . import core, flow

F32 = np.float32

MAX_COUNT = 10.0            # confiance maximale de l'historique
SIGMA_PROX = 0.47           # proximite de l'echantillon (pixels d'affichage)
BOX_T1 = 0.3                # sortie de boite relative -> reactivite totale
RANGE_EPS = 0.02            # plancher de l'etendue locale (test de boite)
FEAT_EPS = 0.01             # plancher de l'etendue locale (caracteristiques)
N_FEATURES = 10

FEATURE_NAMES = [
    "hors_boite", "confiance_flot", "residu_relatif", "ecart_frais",
    "contraste", "historique", "proximite", "mouvement_log2",
    "flou_reechantillonnage", "fixe",
]

# --------------------------------------------------------------------------
# Jitter
# --------------------------------------------------------------------------

GRID_ORDER = {
    2: [(0, 0), (1, 1), (1, 0), (0, 1)],
    3: [(0, 0), (1, 2), (2, 1), (2, 0), (0, 2), (1, 1), (2, 2), (0, 1),
        (1, 0)],
}


def grid_factor(render_size, display_size):
    """Rapport entier (2 ou 3) si la grille ordonnee s'applique, sinon 0."""
    for n in (2, 3):
        if display_size[0] == n * render_size[0] and \
                display_size[1] == n * render_size[1]:
            return n
    return 0


def jitter_plan(render_size, display_size, kind="auto"):
    """(fonction image -> jitter, periode). ``kind`` : ``aucun``, ``grille``,
    ``halton`` ou ``auto`` (grille si le rapport est entier)."""
    if kind == "aucun":
        return (lambda f: (0.0, 0.0)), 0
    n = grid_factor(render_size, display_size)
    if kind in ("auto", "grille") and n:
        order = GRID_ORDER[n]

        def grid(f):
            i, j = order[f % (n * n)]
            return ((i + 0.5) / n - 0.5, (j + 0.5) / n - 0.5)
        return grid, n * n
    phases = core.jitter_phase_count(render_size[0], display_size[0])
    return (lambda f: core.jitter_offset(f, phases)), phases


# --------------------------------------------------------------------------
# Agrandissement spatial de reference (type FSR 1)
# --------------------------------------------------------------------------

def _lanczos2(x):
    x = np.abs(x)
    out = np.where(x < 1e-6, 1.0, np.sinc(x) * np.sinc(x / 2.0))
    return np.where(x < 2.0, out, 0.0)


def lanczos_upscale(img, size):
    """Lanczos-2 separable, borne par le min/max des 4 voisins (pas de
    halos), comme EASU le fait."""
    w, h = size
    sh, sw = img.shape[:2]
    ys, xs = np.mgrid[0:h, 0:w]
    px = (xs + 0.5) / w * sw - 0.5
    py = (ys + 0.5) / h * sh - 0.5
    ix = np.floor(px).astype(np.int64)
    iy = np.floor(py).astype(np.int64)
    fx = px - ix
    fy = py - iy
    acc = np.zeros((h, w, img.shape[2]))
    wsum = np.zeros((h, w))
    for j in range(-1, 3):
        wy = _lanczos2(j - fy)
        qy = np.clip(iy + j, 0, sh - 1)
        for i in range(-1, 3):
            wgt = wy * _lanczos2(i - fx)
            acc += img[qy, np.clip(ix + i, 0, sw - 1)] * wgt[..., None]
            wsum += wgt
    out = acc / wsum[..., None]
    near = [img[np.clip(iy + b, 0, sh - 1), np.clip(ix + a, 0, sw - 1)]
            for a in (0, 1) for b in (0, 1)]
    lo = np.minimum.reduce(near)
    hi = np.maximum.reduce(near)
    return np.clip(out, lo, hi).astype(np.float32)


def rcas(img, amount=1.0):
    """Accentuation RCAS de FSR 1 (croix de 5 pixels, lobe limite).
    ``amount`` : 0 = rien, 1 = lobe maximal de FSR 1 (0 stop)."""
    h, w = img.shape[:2]
    ys, xs = np.mgrid[0:h, 0:w]
    b = img[np.clip(ys - 1, 0, h - 1), xs]
    d = img[ys, np.clip(xs - 1, 0, w - 1)]
    e = img
    f = img[ys, np.clip(xs + 1, 0, w - 1)]
    hh = img[np.clip(ys + 1, 0, h - 1), xs]
    mn4 = np.minimum(np.minimum(b, d), np.minimum(f, hh))
    mx4 = np.maximum(np.maximum(b, d), np.maximum(f, hh))
    hit_min = mn4 / np.maximum(4.0 * mx4, 1e-6)
    hit_max = (1.0 - mx4) / np.minimum(4.0 * mn4 - 4.0, -1e-6)
    lobe_rgb = np.maximum(-hit_min, hit_max)
    lobe = np.clip(np.max(lobe_rgb, axis=-1), -0.1875, 0.0) * amount
    lobe = lobe[..., None]
    return ((lobe * (b + d + f + hh) + e) / (4.0 * lobe + 1.0)).astype(
        np.float32)


def spatial_upscale(img, size, amount=0.87):
    """Lanczos + RCAS ; 0.87 = reglage par defaut de FSR 1 (0,2 stop)."""
    return np.clip(rcas(lanczos_upscale(img, size), amount), 0.0, 1.0)


# --------------------------------------------------------------------------
# USR Universel
# --------------------------------------------------------------------------

def _sat(x):
    return np.clip(x, 0.0, 1.0)


def _logit(p):
    p = np.clip(p, F32(1e-3), F32(1.0 - 1e-3))
    return np.log(p / (F32(1.0) - p)).astype(F32)


def _sigmoid(x):
    return (F32(1.0) / (F32(1.0) + np.exp(-x))).astype(F32)


def lanczos2_weight(x):
    """Lanczos-2 (sinc(x) sinc(x/2)), sous la forme du shader."""
    x = np.abs(x).astype(F32)
    pix = F32(np.pi) * x
    safe = np.maximum(pix, F32(1e-4))
    v = F32(2.0) * np.sin(safe) * np.sin(safe * F32(0.5)) / (safe * safe)
    v = np.where(pix < F32(1e-4), F32(1.0), v)
    return np.where(x < F32(2.0), v, F32(0.0)).astype(F32)


def residual_pass(S, jflag, motion_px, conf, history, jitter):
    """Passe « residu » (resolution de rendu).

    Renvoie (residu YCoCg, sortie de boite relative, valide). La prediction
    est l'historique (resolution d'affichage) lu avec Catmull-Rom a la
    position qu'avait, a l'image precedente, le point echantillonne."""
    rh, rw = S.shape[:2]
    ys, xs = np.mgrid[0:rh, 0:rw]
    jx, jy = F32(jitter[0]), F32(jitter[1])
    su = (xs.astype(F32) + F32(0.5) + jx * jflag) / F32(rw)
    sv = (ys.astype(F32) + F32(0.5) + jy * jflag) / F32(rh)
    pu = su - motion_px[..., 0] / F32(rw)
    pv = sv - motion_px[..., 1] / F32(rh)
    inside = (pu >= 0.0) & (pu <= 1.0) & (pv >= 0.0) & (pv <= 1.0)
    pred = core.sample_catmull_rom(history[..., :3], pu, pv)
    res = (S - pred).astype(F32)
    mn = np.full(S.shape, np.inf, F32)
    mx = np.full(S.shape, -np.inf, F32)
    for dy in (-1, 0, 1):
        qy = np.clip(ys + dy, 0, rh - 1)
        for dx in (-1, 0, 1):
            c = S[qy, np.clip(xs + dx, 0, rw - 1)]
            mn = np.minimum(mn, c)
            mx = np.maximum(mx, c)
    out = np.maximum(np.maximum(mn - pred, pred - mx), F32(0.0))
    box = np.max(out / (mx - mn + F32(RANGE_EPS)), axis=-1).astype(F32)
    box = np.where(inside, box, F32(1e3))
    # stockes ensemble en RGBA16F sur le GPU
    return core.as_f16(res), core.as_f16(box), inside


class UniversalUpscaler:
    """Etat persistant d'une instance (comme usr::Context).

    Reglages modifiables entre deux images : ``net_strength`` (0 =
    heuristique seule), ``max_count`` (longueur d'historique), ``box_t1``
    (anti-fantomes : plus petit = plus reactif), ``sharpness`` (0..1),
    ``motion_source`` (``flow`` / ``oracle`` / ``zero``)."""

    def __init__(self, render_size, display_size, network=None,
                 motion_source="flow", period=0, net_strength=1.0,
                 max_count=MAX_COUNT, box_t1=BOX_T1, sharpness=0.0):
        self.render_size = tuple(render_size)
        self.display_size = tuple(display_size)
        self.network = network
        self.motion_source = motion_source
        self.net_strength = net_strength
        self.max_count = max_count
        self.box_t1 = box_t1
        self.sharpness = sharpness
        self.flow = flow.FlowEstimator(render_size, period)
        self.history = None
        dw, dh = display_size
        oy, ox = np.mgrid[0:dh, 0:dw]
        self._u = (ox.astype(F32) + F32(0.5)) / F32(dw)
        self._v = (oy.astype(F32) + F32(0.5)) / F32(dh)

    def reset(self):
        self.history = None
        self.flow.reset()

    # -- mouvement -----------------------------------------------------------

    def _motion(self, image, jitter, true_motion):
        rw, rh = self.render_size
        est = self.flow(image, jitter)
        if self.motion_source == "oracle" and true_motion is not None:
            m = np.stack([true_motion[..., 0] * F32(rw),
                          true_motion[..., 1] * F32(rh)], -1).astype(F32)
            z = np.zeros((rh, rw), F32)
            return {"motion": m, "conf": z, "jflag": np.ones_like(z),
                    "static": z}
        if self.motion_source == "zero":
            z = np.zeros((rh, rw), F32)
            return {"motion": np.zeros((rh, rw, 2), F32), "conf": z,
                    "jflag": np.ones_like(z), "static": z}
        return est

    # -- passe d'accumulation (resolution d'affichage) -------------------------

    def _gather(self, S, R, box, conf, jflag, jitter):
        """Voisinage 4x4 d'echantillons autour de chaque pixel d'affichage,
        a leurs positions reelles (jitter ou non selon le pixel)."""
        rw, rh = self.render_size
        dw, dh = self.display_size
        jx, jy = F32(jitter[0]), F32(jitter[1])
        px = self._u * F32(rw) - F32(0.5)
        py = self._v * F32(rh) - F32(0.5)
        bx = np.floor(px - jx).astype(np.int64)
        by = np.floor(py - jy).astype(np.int64)
        fr = np.zeros((dh, dw, 3), F32)
        fw = np.zeros((dh, dw), F32)
        ur = np.zeros((dh, dw, 3), F32)
        uw = np.zeros((dh, dw), F32)
        dmin = np.full((dh, dw), F32(1e9), F32)
        mn = np.full((dh, dw, 3), np.inf, F32)
        mx = np.full((dh, dw, 3), -np.inf, F32)
        bmax = np.zeros((dh, dw), F32)
        cmax = np.zeros((dh, dw), F32)
        for j in range(-1, 3):
            qy = np.clip(by + j, 0, rh - 1)
            for i in range(-1, 3):
                qx = np.clip(bx + i, 0, rw - 1)
                jf = jflag[qy, qx]
                dx = qx.astype(F32) + jx * jf - px
                dy = qy.astype(F32) + jy * jf - py
                wl = lanczos2_weight(dx) * lanczos2_weight(dy)
                c = S[qy, qx]
                fr = fr + c * wl[..., None]
                fw = fw + wl
                wt = np.maximum(F32(0.0), F32(1.0) - np.abs(dx)) * \
                    np.maximum(F32(0.0), F32(1.0) - np.abs(dy))
                ur = ur + R[qy, qx] * wt[..., None]
                uw = uw + wt
                dmin = np.minimum(dmin, dx * dx + dy * dy)
                if i in (0, 1) and j in (0, 1):
                    mn = np.minimum(mn, c)
                    mx = np.maximum(mx, c)
                    bmax = np.maximum(bmax, box[qy, qx])
                    cmax = np.maximum(cmax, conf[qy, qx])
        fresh = np.clip(fr / np.maximum(fw, F32(1e-6))[..., None], mn, mx)
        upd = ur / np.maximum(uw, F32(1e-6))[..., None]
        return (fresh.astype(F32), upd.astype(F32), dmin, mn, mx, bmax,
                cmax)

    def dispatch(self, image, jitter=(0.0, 0.0), reset=False,
                 true_motion=None, return_internals=False):
        """Une image : ``image`` (h, w, 3) telle que le jeu l'affiche,
        ``jitter`` en pixels de rendu. Renvoie l'image agrandie (RGB)."""
        rw, rh = self.render_size
        dw, dh = self.display_size
        if reset:
            self.reset()
        S = core.rgb_to_ycocg(np.asarray(image, F32)).astype(F32)
        mo = self._motion(image, jitter, true_motion)
        # confiance stockee sur 8 bits (RGBA8 : confiance, jitter, fixe)
        m, conf, jflag = mo["motion"], core.as_unorm8(mo["conf"]), \
            mo["jflag"]
        first = self.history is None
        if first:
            R = np.zeros_like(S)
            box = np.zeros((rh, rw), F32)
        else:
            R, box, _ = residual_pass(S, jflag, m, conf, self.history,
                                      jitter)
        fresh, upd, dmin, mn, mx, bmax, cmax = self._gather(
            S, R, box, conf, jflag, jitter)
        ratio = F32(dw) / F32(rw)
        w = np.exp(-dmin * ratio * ratio /
                   F32(2.0 * SIGMA_PROX * SIGMA_PROX)).astype(F32)

        u, v = self._u, self._v
        rix = np.clip(np.floor(u * F32(rw)).astype(np.int64), 0, rw - 1)
        riy = np.clip(np.floor(v * F32(rh)).astype(np.int64), 0, rh - 1)
        mpx = m[riy, rix]
        pu = u - mpx[..., 0] / F32(rw)
        pv = v - mpx[..., 1] / F32(rh)
        valid = (pu >= 0.0) & (pu <= 1.0) & (pv >= 0.0) & (pv <= 1.0) & (
            not first)
        if first:
            hr = fresh
            nr = np.zeros((dh, dw), F32)
        else:
            hr = core.sample_catmull_rom(self.history[..., :3], pu,
                                         pv).astype(F32)
            nr = core.sample_bilinear(self.history[..., 3], pu,
                                      pv).astype(F32)
        nr = np.where(valid, nr, F32(0.0))

        box_h = _sat(bmax / F32(self.box_t1)).astype(F32)
        react_h = np.where(valid, np.maximum(box_h, cmax), F32(1.0))
        gain_h = (w / (nr + w)).astype(F32)
        rng = (mx - mn)[..., 0]
        feats = features(box_h, cmax, upd, fresh, hr, rng, nr, w, mpx,
                         pu, pv, mo["static"][riy, rix], self.display_size,
                         self.max_count)
        if self.network is not None and self.net_strength > 0.0:
            o = self.network.forward(feats.reshape(-1, N_FEATURES)).reshape(
                dh, dw, 2).astype(F32)
            s = F32(self.net_strength)
            react = _sigmoid(_logit(react_h) + s * o[..., 0])
            gain = _sigmoid(_logit(gain_h) + s * o[..., 1])
            react = np.where(valid, react, F32(1.0))
        else:
            react, gain = react_h, gain_h
        acc = hr + gain[..., None] * upd
        new = acc + (fresh - acc) * react[..., None]
        count = np.minimum(nr * (F32(1.0) - react) + w, F32(self.max_count))
        self.history = core.as_f16(np.concatenate(
            [new, count[..., None]], axis=-1))
        out = output_pass(self.history, self.sharpness)
        if not return_internals:
            return out
        return out, {
            "features": feats, "hr": hr, "upd": upd, "fresh": fresh,
            "react_h": react_h, "gain_h": gain_h, "react": react,
            "gain": gain, "valid": valid, "puv": (pu, pv), "flow": mo,
            "count": count,
        }


def features(box_h, conf, upd, fresh, hr, rng, nr, w, mpx, pu, pv, static,
             display_size, max_count):
    """Les 10 entrees du reseau universel, dans l'ordre du shader."""
    dw, dh = display_size
    den = rng + F32(FEAT_EPS)
    fx = pu * F32(dw) - F32(0.5)
    fy = pv * F32(dh) - F32(0.5)
    fx = fx - np.floor(fx)
    fy = fy - np.floor(fy)
    mlen = np.sqrt(mpx[..., 0] * mpx[..., 0] + mpx[..., 1] * mpx[..., 1])
    return np.stack([
        box_h,
        conf,
        np.minimum(np.abs(upd[..., 0]) / den, F32(8.0)),
        np.minimum(np.abs(fresh[..., 0] - hr[..., 0]) / den, F32(8.0)),
        np.minimum(F32(4.0) * rng, F32(1.0)),
        nr / F32(max_count),
        w,
        np.log2(F32(1.0) + mlen),
        F32(4.0) * fx * (F32(1.0) - fx) + F32(4.0) * fy * (F32(1.0) - fy),
        static,
    ], axis=-1).astype(F32)


def output_pass(history, sharpness=0.0):
    """YCoCg -> RGB, borne a [0, 1], accentuation RCAS optionnelle."""
    rgb = np.clip(core.ycocg_to_rgb(history[..., :3]), 0.0, 1.0)
    if sharpness > 0.0:
        rgb = np.clip(rcas(rgb, sharpness), 0.0, 1.0)
    return rgb.astype(F32)


# --------------------------------------------------------------------------
# Banc de bout en bout (bibliotheque C++ reelle) : tests/wine/
# --------------------------------------------------------------------------

BANC_MAGIC = 0x55525355     # 'USRU'
BANC_RESET_FRAME = 12


def banc_sequence(frames=16, render_size=(192, 108), display_size=(384, 216),
                  seed=101):
    """Sequence deterministe pour le banc : jeu emule (scene realiste),
    jitter en grille sur la scene 3D seulement (HUD fixe), comme Xenia au
    niveau 2. Renvoie (images 8 bits, jitters, periode)."""
    from . import emul
    from .scene_realiste import RealisticScene
    game = emul.EmulatedGame(RealisticScene(seed=seed))
    jit, period = jitter_plan(render_size, display_size, "grille")
    images, jitters = [], []
    for f in range(frames):
        j = jit(f)
        img, _, _ = game.frame(float(f), render_size, j, lod_bias=-1.0,
                               hud_jitter=False)
        images.append(np.round(img * 255.0).astype(np.uint8))
        jitters.append((np.float32(j[0]), np.float32(j[1])))
    return images, jitters, period


def write_banc_input(path, images, jitters, render_size, display_size,
                     period, no_network=False, reset=True, sharpness=0.5):
    rw, rh = render_size
    dw, dh = display_size
    flags = (1 if no_network else 0) | (2 if reset else 0) | (
        int(round(sharpness * 255)) << 8)
    with open(path, "wb") as f:
        f.write(np.array([BANC_MAGIC, rw, rh, dw, dh, len(images), period,
                          flags], "<u4").tobytes())
        for img, j in zip(images, jitters):
            f.write(np.array(j, "<f4").tobytes())
            rgba = np.concatenate([img, np.full(img.shape[:2] + (1,), 255,
                                                np.uint8)], axis=-1)
            f.write(np.ascontiguousarray(rgba).tobytes())


def read_banc_output(path, display_size, frames):
    dw, dh = display_size
    data = np.fromfile(path, "<f2").astype(np.float32)
    return data.reshape(frames, dh, dw, 4)[..., :3]


def banc_reference(images, jitters, render_size, display_size, period,
                   network, reset=True, sharpness=0.5):
    """Ce que la bibliotheque doit produire, image par image."""
    up = UniversalUpscaler(render_size, display_size, network=network,
                           period=period, sharpness=sharpness)
    outs = []
    for f, (img, j) in enumerate(zip(images, jitters)):
        x = img.astype(np.float32) / np.float32(255.0)
        outs.append(up.dispatch(x, (float(j[0]), float(j[1])),
                                reset=reset and f == BANC_RESET_FRAME))
    return outs
