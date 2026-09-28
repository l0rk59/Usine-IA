"""Scene de test procedurale : ce qu'un moteur de jeu donnerait a l'upscaler.

Deux plans : un decor lointain qui defile avec la camera, et des objets
proches qui se deplacent et se croisent (donc des zones desoccluses a
chaque image). Le decor contient exactement ce qui fait souffrir un
upscaler : rayures fines, lignes plus fines qu'un pixel de rendu, points
tres lumineux (HDR), aplats.

Tout est analytique : couleur, profondeur et vecteurs de mouvement sont
exacts, et la verite terrain est obtenue par sur-echantillonnage 4x4 a la
resolution d'affichage.
"""

import numpy as np

BACKGROUND_DEPTH = 20.0


class Scene:
    def __init__(self, seed=0, camera_speed=(0.006, 0.002), wobble=0.004,
                 n_objects=4, object_speed=1.0, static=False, aspect=16 / 9,
                 cache_gt=False):
        rng = np.random.default_rng(seed)
        self._gt_cache = {} if cache_gt else None
        self.aspect = aspect
        self.static = static
        self.camera_speed = np.array(camera_speed, np.float64)
        self.wobble = wobble
        self.cam0 = rng.uniform(0.0, 3.0, 2)
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
                "tint": rng.uniform(0.25, 1.0, 3),
                "rings": rng.uniform(25.0, 45.0),
            })

    # --- mouvement --------------------------------------------------------

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

    # --- textures ---------------------------------------------------------

    @staticmethod
    def _background(wx, wy):
        base = np.stack([0.35 + 0.15 * np.sin(1.3 * wx),
                         0.30 + 0.12 * np.sin(1.1 * wy + 1.0),
                         0.40 + 0.15 * np.cos(0.7 * (wx + wy))], axis=-1)
        checker = ((np.floor(wx / 0.1) + np.floor(wy / 0.1)) % 2) * 0.25 + 0.75
        col = base * checker[..., None]

        # rayures fines (periode ~1.8 pixel de rendu en mode performance)
        band = (np.floor(wy / 0.3) % 3) == 0
        stripes = 0.5 + 0.5 * np.sin(2 * np.pi * wx / 0.025)
        col = np.where(band[..., None],
                       col * (0.35 + 0.65 * stripes[..., None]), col)

        # grille de lignes plus fines qu'un pixel de rendu (cables, grillage)
        gx = np.abs((wx / 0.22) - np.round(wx / 0.22)) * 0.22
        gy = np.abs((wy / 0.18) - np.round(wy / 0.18)) * 0.18
        line = (gx < 0.002) | (gy < 0.002)
        col = np.where(line[..., None], np.array([0.95, 0.9, 0.7]), col)

        # points HDR (reflets, lampes)
        cx = np.round(wx / 0.37) * 0.37
        cy = np.round(wy / 0.29) * 0.29
        spot = (wx - cx) ** 2 + (wy - cy) ** 2 < 0.006 ** 2
        col = np.where(spot[..., None], np.array([6.0, 5.0, 3.5]), col)
        return col

    @staticmethod
    def _object(obj, lx, ly):
        r = np.sqrt(lx * lx + ly * ly)
        rings = 0.55 + 0.45 * np.sin(obj["rings"] * r)
        diag = 0.6 + 0.4 * (np.floor((lx + ly) * 9.0) % 2)
        pattern = rings if obj["shape"] == "disc" else diag
        return obj["tint"] * pattern[..., None]

    @staticmethod
    def _animated(color, wx, wy, t):
        """Contenus qui changent SANS vecteur de mouvement : un ecran qui
        defile et un neon qui clignote. Les jeux en sont pleins (eau,
        particules, ecrans, lumieres) ; seul le recadrage de l'historique
        evite alors les trainees fantomes."""
        px = wx % 1.7
        py = wy % 1.3
        screen = (px > 0.9) & (px < 1.45) & (py > 0.25) & (py < 0.6)
        scroll = 0.5 + 0.5 * np.sin(2 * np.pi * (px * 7.0 + py * 2.0
                                                   - 0.09 * t))
        screen_col = np.stack([0.2 + 0.8 * scroll, 0.9 * scroll ** 2,
                               1.0 - 0.7 * scroll], axis=-1)
        color = np.where(screen[..., None], screen_col, color)

        neon = (px > 0.2) & (px < 0.7) & (np.abs(py - 0.95) < 0.012)
        on = (int(np.floor(t / 7.0)) % 2) == 0
        neon_col = np.array([3.0, 0.4, 2.2]) if on else np.array(
            [0.25, 0.05, 0.2])
        return np.where(neon[..., None], neon_col, color)

    # --- rendu ------------------------------------------------------------

    def shade(self, t, u, v):
        """Couleur, 1/profondeur et mouvement (uv) aux positions (u, v)."""
        cam, cam_prev = self.camera(t), self.camera(t - 1)
        wx = u * self.aspect + cam[0]
        wy = v + cam[1]
        color = self._animated(self._background(wx, wy), wx, wy, t)
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
            color = np.where(inside[..., None], self._object(obj, lx, ly),
                             color)
            depth = np.where(inside, obj["depth"], depth)
            mu = np.where(inside, c[0] - cp[0], mu)
            mv = np.where(inside, c[1] - cp[1], mv)

        motion = np.stack([mu, mv], axis=-1)
        return (color.astype(np.float32), (1.0 / depth).astype(np.float32),
                motion.astype(np.float32))

    def render(self, t, size, jitter=(0.0, 0.0)):
        """Un echantillon par pixel, decale par le jitter : l'image aliasee
        que le moteur rend en basse resolution."""
        w, h = size
        ys, xs = np.mgrid[0:h, 0:w]
        return self.shade(t, (xs + 0.5 + jitter[0]) / w,
                          (ys + 0.5 + jitter[1]) / h)

    def ground_truth(self, t, size, ss=4):
        """Image de reference a la resolution d'affichage (anticrenelee)."""
        key = (t, tuple(size), ss)
        if self._gt_cache is not None and key in self._gt_cache:
            return self._gt_cache[key]
        w, h = size
        ys, xs = np.mgrid[0:h, 0:w]
        acc = np.zeros((h, w, 3), np.float64)
        for j in range(ss):
            for i in range(ss):
                c, _, _ = self.shade(t, (xs + (i + 0.5) / ss) / w,
                                     (ys + (j + 0.5) / ss) / h)
                acc += c
        gt = (acc / (ss * ss)).astype(np.float32)
        if self._gt_cache is not None:
            self._gt_cache[key] = gt
        return gt
