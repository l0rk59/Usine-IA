"""Comportement de la reference NumPy (l'algorithme lui-meme)."""

import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from usr_ref import core, evaluate  # noqa: E402
from usr_ref.network import Network, load_default  # noqa: E402
from usr_ref.scene import Scene  # noqa: E402


class Couleurs(unittest.TestCase):
    def test_compression_reversible(self):
        c = np.random.default_rng(0).uniform(0, 50, (100, 3))
        np.testing.assert_allclose(core.untonemap(core.tonemap(c)), c,
                                   rtol=1e-5)

    def test_ycocg_reversible(self):
        c = np.random.default_rng(1).uniform(0, 1, (100, 3))
        np.testing.assert_allclose(core.ycocg_to_rgb(core.rgb_to_ycocg(c)),
                                   c, atol=1e-12)


class AidesHote(unittest.TestCase):
    def test_tailles_de_rendu(self):
        self.assertEqual(core.render_size((3840, 2160), "performance"),
                         (1920, 1080))
        self.assertEqual(core.render_size((3840, 2160), "ultra"),
                         (1280, 720))
        self.assertEqual(core.render_size((3840, 2160), "natif"),
                         (3840, 2160))

    def test_jitter_dans_le_pixel_et_bien_reparti(self):
        n = core.jitter_phase_count(1920, 3840)
        self.assertEqual(n, 32)
        pts = np.array([core.jitter_offset(i, n) for i in range(n)])
        self.assertTrue(np.all(np.abs(pts) <= 0.5))
        # chaque quart du pixel recoit des echantillons
        quad = (pts[:, 0] > 0).astype(int) * 2 + (pts[:, 1] > 0)
        self.assertEqual(len(set(quad.tolist())), 4)
        self.assertEqual(core.jitter_offset(0, n), core.jitter_offset(n, n))


class Echantillonnage(unittest.TestCase):
    def test_catmull_rom_exact_aux_centres(self):
        tex = np.random.default_rng(2).uniform(0, 1, (9, 11, 3))
        ys, xs = np.mgrid[0:9, 0:11]
        out = core.sample_catmull_rom(tex, (xs + 0.5) / 11, (ys + 0.5) / 9)
        np.testing.assert_allclose(out, tex, atol=1e-6)

    def test_bilineaire_moyenne_au_milieu(self):
        tex = np.array([[0.0, 1.0], [2.0, 3.0]])
        v = core.sample_bilinear(tex, np.array([0.5]), np.array([0.5]))
        self.assertAlmostEqual(float(v[0]), 1.5)

    def test_recadrage_dans_la_boite(self):
        h = np.array([[2.0, 0.0, 0.0]])
        out = core.clip_to_box(h, np.zeros((1, 3)), np.ones((1, 3)))
        self.assertTrue(np.all(out <= 1.0 + 1e-4))
        inside = np.array([[0.5, 0.5, 0.5]])
        np.testing.assert_allclose(
            core.clip_to_box(inside, np.zeros((1, 3)), np.ones((1, 3))),
            inside)


class Passe1(unittest.TestCase):
    def test_vecteur_du_voisin_le_plus_proche(self):
        invz = np.full((5, 5), 0.05, np.float32)
        invz[2, 2] = 0.5                       # un point proche au centre
        motion = np.zeros((5, 5, 2), np.float32)
        motion[2, 2] = (0.1, 0.0)
        mv, dz, _ = core.prepare(invz, motion, invz, (0, 0), True)
        # tout le voisinage 3x3 suit le point proche
        self.assertTrue(np.allclose(mv[1:4, 1:4, 0], 0.1, atol=1e-3))
        self.assertAlmostEqual(float(mv[0, 0, 0]), 0.0)
        self.assertAlmostEqual(float(dz[1, 1]), 0.5)

    def test_desocclusion(self):
        # image precedente : un objet proche couvrait les colonnes 0..3
        prev = np.full((4, 12), 0.05, np.float32)
        prev[:, :4] = 0.5
        # maintenant il a disparu : le fond decouvert est desoccluse
        cur = np.full((4, 12), 0.05, np.float32)
        motion = np.zeros((4, 12, 2), np.float32)
        _, _, dis = core.prepare(cur, motion, prev, (0, 0), False)
        self.assertTrue(np.all(dis[:, 1:3] > 0.99))
        self.assertTrue(np.all(dis[:, 6:] < 0.01))

    def test_reset_rejette_tout(self):
        z = np.full((4, 4), 0.1, np.float32)
        _, _, dis = core.prepare(z, np.zeros((4, 4, 2), np.float32), z,
                                 (0, 0), True)
        self.assertTrue(np.all(dis == 1.0))


class Accumulation(unittest.TestCase):
    SIZE = (128, 72)

    @classmethod
    def setUpClass(cls):
        cls.net = load_default()

    def test_premiere_image_sans_historique(self):
        rsize = core.render_size(self.SIZE, "performance")
        scene = Scene(seed=7)
        color, invz, motion = scene.render(0, rsize)
        up = core.Upscaler(rsize, self.SIZE, network=self.net)
        out, info = up.dispatch(color, invz, motion, (0, 0),
                                return_internals=True)
        self.assertTrue(np.all(info["alpha"] == 1.0))
        self.assertFalse(np.any(info["valid"]))
        self.assertTrue(np.all(np.isfinite(out)))

    def test_heuristique_sans_regression(self):
        # Seule, l'heuristique n'est qu'au niveau du bilineaire en PSNR
        # (son recadrage efface les details fins) : c'est le role du
        # reseau de faire mieux. On verifie qu'elle ne se degrade pas.
        scene = Scene(seed=11, cache_gt=True)
        bil = evaluate.run(scene, self.SIZE, "performance", 24, "bilineaire")
        heu = evaluate.run(scene, self.SIZE, "performance", 24,
                           "heuristique")
        self.assertGreater(heu["psnr"], bil["psnr"] - 1.0)
        self.assertLess(heu["scintillement"], bil["scintillement"])

    def test_reseau_neutre_egal_heuristique(self):
        rsize = core.render_size(self.SIZE, "performance")
        scene = Scene(seed=5)
        a = core.Upscaler(rsize, self.SIZE)
        b = core.Upscaler(rsize, self.SIZE, network=Network.zeros())
        for f in range(4):
            j = core.jitter_offset(f, 32)
            args = scene.render(f, rsize, j) + (j,)
            np.testing.assert_allclose(b.dispatch(*args), a.dispatch(*args),
                                       atol=2e-3)

    @unittest.skipIf(load_default() is None, "poids absents")
    def test_le_reseau_ameliore_l_image(self):
        for static in (True, False):
            scene = Scene(seed=303, static=static, cache_gt=True)
            heu = evaluate.run(scene, self.SIZE, "performance", 24,
                               "heuristique")
            ia = evaluate.run(scene, self.SIZE, "performance", 24, "ia",
                              self.net)
            bil = evaluate.run(scene, self.SIZE, "performance", 24,
                               "bilineaire")
            label = "camera %s" % ("fixe" if static else "mobile")
            self.assertGreater(ia["psnr"], heu["psnr"] + 1.0, label)
            self.assertGreater(ia["psnr"], bil["psnr"] + 1.0, label)

    def test_hdr_et_accentuation_restent_finis(self):
        rsize = core.render_size(self.SIZE, "qualite")
        scene = Scene(seed=9)
        up = core.Upscaler(rsize, self.SIZE, network=self.net)
        for f in range(3):
            j = core.jitter_offset(f, 8)
            color, invz, motion = scene.render(f, rsize, j)
            out = up.dispatch(color * 50.0, invz, motion, j, sharpness=1.0,
                              exposure=0.5)
            self.assertTrue(np.all(np.isfinite(out)))
            self.assertTrue(np.all(out >= 0.0))


if __name__ == "__main__":
    unittest.main()
