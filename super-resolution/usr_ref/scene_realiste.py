"""Scene de test « realiste » : rendue comme par un vrai GPU de jeu.

La scene de ``scene.py`` est un test de resistance : ses textures ne sont
pas filtrees du tout, ce qu'aucun jeu ne fait. Ici, comme un GPU avec ses
mip-maps, chaque texture est pre-filtree selon la taille du pixel : les
details plus fins que le pixel s'estompent au lieu de crenerer. Restent
crenelees, comme dans un jeu sans anticrenelage : les silhouettes, les
fils fins, les aretes. C'est l'image typique d'un jeu Xbox 360 en 720p.

Contenu : un decor lointain (bruit fractal colore, immeubles aux fenetres
regulieres, fils electriques), des objets proches qui se deplacent et se
croisent (textures de briques et d'anneaux), un ecran anime et un neon
sans vecteurs de mouvement. Mouvement et profondeur restent analytiques.
"""

import numpy as np

BACKGROUND_DEPTH = 20.0


def _atten(freq, footprint):
    """Reponse d'un pre-filtre gaussien (type mip-map) a la frequence donnee
    (cycles par unite), pour un pixel de ``footprint`` unites."""
    sigma = 0.45 * footprint
    return np.exp(-2.0 * (np.pi * freq * sigma) ** 2)


def _smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


class RealisticScene:
    def __init__(self, seed=0, camera_speed=(0.006, 0.002), wobble=0.004,
                 n_objects=4, object_speed=1.0, static=False, aspect=16 / 9):
        rng = np.random.default_rng(seed + 7919)
        self.aspect = aspect
        self.static = static
        self.camera_speed = np.array(camera_speed, np.float64)
        self.wobble = wobble
        self.cam0 = rng.uniform(0.0, 3.0, 2)
        # bruit fractal : octaves de sinusoides orientees
        self.octaves = []
        for k in range(7):
            f = 1.6 * 2.0 ** k
            for _ in range(3):
                ang = rng.uniform(0, np.pi)
                self.octaves.append((f * np.cos(ang), f * np.sin(ang), f,
                                     rng.uniform(0, 2 * np.pi),
                                     0.55 ** k))
        self.palette = rng.uniform(0.15, 0.75, (3, 3))
        # immeubles : rectangles du decor (monde), fenetres regulieres
        self.buildings = []
        for _ in range(9):
            x0 = rng.uniform(0.0, 6.0)
            self.buildings.append((x0, x0 + rng.uniform(0.25, 0.6),
                                   rng.uniform(0.35, 0.8),
                                   rng.uniform(0.2, 0.5, 3)))
        self.objects = []
        for k in range(n_objects):
            self.objects.append({
                "shape": "disc" if k % 2 == 0 else "box",
                "base": rng.uniform(0.2, 0.8, 2),
                "amp": rng.uniform(0.1, 0.3, 2) * object_speed,
                "freq": rng.uniform(0.02, 0.05, 2),
                "phase": rng.uniform(0, 2 * np.pi, 2),
                "radius": rng.uniform(0.08, 0.16),
                "depth": 4.0 + 1.5 * k,
                "tint": rng.uniform(0.3, 1.0, 3),
                "rings": rng.uniform(20.0, 40.0),
            })

    # --- mouvement (meme modele que scene.Scene) ---------------------------

    def camera(self, t):
        if self.static:
            return self.cam0.copy()
        return (self.cam0 + self.camera_speed * t
                + self.wobble * np.array([np.sin(0.13 * t),
                                          np.cos(0.09 * t)]))

    def object_center(self, obj, t):
        if self.static:
            t = 0.0
        return obj["base"] + obj["amp"] * np.sin(obj["freq"] * t
                                                 + obj["phase"])

    # --- textures filtrees ----------------------------------------------------

    def _noise(self, wx, wy, fp):
        acc = np.zeros(wx.shape)
        for kx, ky, f, ph, amp in self.octaves:
            acc += amp * _atten(f, fp) * np.sin(2 * np.pi * (kx * wx + ky * wy)
                                                 + ph)
        return acc

    def _background(self, wx, wy, fp):
        n = self._noise(wx, wy, fp)
        t = np.clip(0.5 + 0.35 * n, 0.0, 1.0)[..., None]
        p = self.palette
        col = np.where(t < 0.5, p[0] + (p[1] - p[0]) * (t / 0.5),
                       p[1] + (p[2] - p[1]) * ((t - 0.5) / 0.5))
        # horizon : sol plus sombre en bas du decor (arete nette)
        ground = (wy % 2.0) > 1.35
        col = np.where(ground[..., None], col * 0.55, col)
        # immeubles : silhouettes nettes, fenetres en texture filtree
        wxm = wx % 6.5
        for x0, x1, top, tint in self.buildings:
            inside = (wxm > x0) & (wxm < x1) & ((wy % 2.0) > top) & (
                (wy % 2.0) < 1.35)
            fwin = 28.0
            a = _atten(fwin, fp)
            win = (0.5 + 0.5 * a * np.cos(2 * np.pi * fwin * wxm)) * (
                0.5 + 0.5 * a * np.cos(2 * np.pi * fwin * wy))
            bcol = tint * (0.55 + 0.9 * win)[..., None]
            col = np.where(inside[..., None], bcol, col)
        # fils electriques : plus fins qu'un pixel -> crenelent (realiste)
        for slope, off in ((0.08, 0.28), (-0.05, 0.62)):
            d = np.abs((wy % 2.0) - (off + slope * (wx % 2.0)))
            col = np.where((d < 0.0022)[..., None],
                           np.array([0.08, 0.08, 0.1]), col)
        return col

    def _animated(self, col, wx, wy, t, fp):
        px = wx % 1.7
        py = wy % 1.3
        screen = (px > 0.9) & (px < 1.45) & (py > 0.25) & (py < 0.6)
        f = 7.0
        s = 0.5 + 0.5 * _atten(f, fp) * np.sin(
            2 * np.pi * (px * f + py * 2.0 - 0.09 * t))
        screen_col = np.stack([0.2 + 0.8 * s, 0.9 * s * s, 1.0 - 0.7 * s],
                              axis=-1)
        col = np.where(screen[..., None], screen_col, col)
        neon = (px > 0.2) & (px < 0.7) & (np.abs(py - 0.95) < 0.012)
        on = (int(np.floor(t / 7.0)) % 2) == 0
        neon_col = np.array([3.0, 0.4, 2.2]) if on else np.array(
            [0.25, 0.05, 0.2])
        return np.where(neon[..., None], neon_col, col)

    @staticmethod
    def _object(obj, lx, ly, fp_local):
        if obj["shape"] == "disc":
            r = np.sqrt(lx * lx + ly * ly)
            f = obj["rings"] / (2 * np.pi)
            pattern = 0.55 + 0.45 * _atten(f, fp_local) * np.sin(
                obj["rings"] * r)
        else:
            f = 4.5
            a = _atten(f, fp_local)
            brick = (0.5 + 0.5 * a * np.sin(2 * np.pi * f * ly)) * (
                0.5 + 0.5 * a * np.sin(2 * np.pi * f * 0.5 * lx
                                       + np.pi * np.floor(ly * f)))
            pattern = 0.45 + 0.55 * brick
        return obj["tint"] * pattern[..., None]

    # --- rendu ---------------------------------------------------------------

    def shade(self, t, u, v, footprint=None):
        """Couleur, 1/z et mouvement (uv) ; ``footprint`` = taille du pixel
        en unites d'ecran (hauteur), pour le pre-filtrage des textures."""
        fp = 0.0 if footprint is None else footprint
        cam, cam_prev = self.camera(t), self.camera(t - 1)
        wx = u * self.aspect + cam[0]
        wy = v + cam[1]
        color = self._animated(self._background(wx, wy, fp), wx, wy, t, fp)
        depth = np.full(u.shape, BACKGROUND_DEPTH)
        mu = np.full(u.shape, -(cam[0] - cam_prev[0]) / self.aspect)
        mv = np.full(u.shape, -(cam[1] - cam_prev[1]))
        for obj in sorted(self.objects, key=lambda o: -o["depth"]):
            c = self.object_center(obj, t)
            cp = self.object_center(obj, t - 1)
            lx = (u - c[0]) * self.aspect / obj["radius"]
            ly = (v - c[1]) / obj["radius"]
            if obj["shape"] == "disc":
                inside = lx * lx + ly * ly < 1.0
            else:
                inside = (np.abs(lx) < 1.0) & (np.abs(ly) < 0.7)
            inside &= obj["depth"] < depth
            color = np.where(inside[..., None],
                             self._object(obj, lx, ly, fp / obj["radius"]),
                             color)
            depth = np.where(inside, obj["depth"], depth)
            mu = np.where(inside, c[0] - cp[0], mu)
            mv = np.where(inside, c[1] - cp[1], mv)
        return (color.astype(np.float32), (1.0 / depth).astype(np.float32),
                np.stack([mu, mv], axis=-1).astype(np.float32))
