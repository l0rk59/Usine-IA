"""Tests de USR Universel (reference NumPy) : estimateur de mouvement et
accumulation, sans GPU. Tailles reduites pour rester rapides."""

import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from usr_ref import emul, flow, universel  # noqa: E402
from usr_ref.scene_realiste import RealisticScene  # noqa: E402

RS = (96, 54)
DS = (192, 108)


def texture(w, h, dx=0.0, dy=0.0, seed=0):
    """Texture lisse et riche (somme de sinusoides), decalee de (dx, dy)
    pixels : le contenu du pixel p est celui du pixel p - d de l'image non
    decalee."""
    rng = np.random.default_rng(seed)
    ys, xs = np.mgrid[0:h, 0:w].astype(np.float64)
    x = xs - dx
    y = ys - dy
    acc = np.zeros((h, w))
    for _ in range(12):
        f = rng.uniform(0.03, 0.16)
        a = rng.uniform(0, np.pi)
        acc += np.sin(2 * np.pi * f * (np.cos(a) * x + np.sin(a) * y)
                      + rng.uniform(0, 6.3))
    v = 0.5 + 0.08 * acc
    img = np.stack([v, 0.8 * v + 0.1, 1.0 - 0.6 * v], -1)
    return emul.quantize(np.clip(img, 0, 1))


class Flot(unittest.TestCase):
    def test_translation_sous_pixel(self):
        """Mouvement de scene connu (0,6 ; -0,35) px : retrouve a < 0,1 px
        pres a l'interieur de l'image."""
        est = flow.FlowEstimator(RS)
        est(texture(*RS))
        out = est(texture(*RS, dx=0.6, dy=-0.35))
        m = out["motion"][6:-6, 6:-6]
        err = np.hypot(m[..., 0] - 0.6, m[..., 1] + 0.35)
        self.assertLess(float(np.median(err)), 0.1)
        self.assertLess(float(np.mean(err > 0.5)), 0.05)
        self.assertLess(float(np.mean(out["conf"][6:-6, 6:-6])), 0.2)

    def test_grand_deplacement(self):
        """5 px par image : trouve par la recherche du niveau grossier."""
        est = flow.FlowEstimator(RS)
        est(texture(*RS))
        m = est(texture(*RS, dx=5.0, dy=2.0))["motion"][8:-8, 8:-8]
        self.assertLess(float(np.median(np.hypot(m[..., 0] - 5.0,
                                                 m[..., 1] - 2.0))), 0.15)

    def test_image_fixe(self):
        est = flow.FlowEstimator(RS)
        img = texture(*RS)
        est(img)
        out = est(img)
        self.assertTrue(np.all(out["motion"] == 0.0))
        self.assertTrue(np.all(out["static"] == 1.0))
        self.assertTrue(np.all(out["conf"] == 0.0))

    def test_hud_sans_jitter(self):
        """Jitter injecte sur la scene, pas sur le HUD : les pixels du HUD
        (identiques d'une image a l'autre) sont marques « hors jitter »."""
        est = flow.FlowEstimator(RS, period=4)
        a = texture(*RS)
        b = texture(*RS, dx=-0.5, dy=0.0)   # scene immobile, jitter +0,5
        hud = np.zeros(RS[::-1], bool)
        hud[5:15, 5:40] = True
        b = np.where(hud[..., None], a, b)
        est(a, (0.0, 0.0))
        out = est(b, (0.5, 0.0))
        inner = np.zeros_like(hud)
        inner[7:13, 7:38] = True        # coeur du HUD (motif 5x5 entier)
        self.assertTrue(np.all(out["jflag"][inner] == 0.0))
        # f = 0 : mouvement de scene = difference de jitter (0,5 ; 0)
        self.assertTrue(np.all(out["motion"][inner][:, 0] == np.float32(0.5)))
        self.assertTrue(np.all(out["motion"][inner][:, 1] == 0.0))
        loin = np.zeros_like(hud)
        loin[30:, 50:] = True
        self.assertTrue(np.all(out["jflag"][loin] == 1.0))
        # scene immobile sous jitter : mouvement de scene ~ 0
        self.assertLess(float(np.median(np.abs(out["motion"][loin]))), 0.1)

    def test_meme_phase(self):
        """Grille 2x2 sur une scene immobile : a partir de la 5e image, le
        test exact « meme phase » fige le mouvement a zero."""
        jit, period = universel.jitter_plan(RS, DS, "grille")
        self.assertEqual(period, 4)
        est = flow.FlowEstimator(RS, period=period)
        for f in range(6):
            j = jit(f)
            out = est(texture(*RS, dx=-j[0], dy=-j[1]), j)
        self.assertTrue(np.all(out["motion"] == 0.0))
        self.assertTrue(np.all(out["static"] == 1.0))

    def test_insensible_a_l_arrondi(self):
        """Un ulp de difference sur l'entree (conversion UNORM d'un autre
        GPU) ne change pas le mouvement : luminance entiere et couts
        compares a resolution fixe."""
        a = texture(*RS)
        b = texture(*RS, dx=0.37, dy=0.21)
        rng = np.random.default_rng(1)

        def bump(x):
            m = rng.uniform(size=x.shape) < 0.2
            return np.where(m, np.nextafter(x, np.float32(2)), x).astype(
                np.float32)

        e1, e2 = flow.FlowEstimator(RS), flow.FlowEstimator(RS)
        e1(a)
        e2(bump(a))
        self.assertTrue(np.array_equal(e1(b)["motion"], e2(bump(b))["motion"]))


class Jitter(unittest.TestCase):
    def test_grille_couvre_les_centres(self):
        """Rapport 3 : les 9 positions de la grille tombent exactement sur
        les centres des 3x3 pixels d'affichage de chaque pixel de rendu."""
        jit, period = universel.jitter_plan((128, 72), (384, 216), "auto")
        self.assertEqual(period, 9)
        pts = sorted(jit(f) for f in range(9))
        expect = sorted(((i + 0.5) / 3 - 0.5, (j + 0.5) / 3 - 0.5)
                        for i in range(3) for j in range(3))
        np.testing.assert_allclose(pts, expect, atol=1e-12)

    def test_rapport_non_entier(self):
        jit, period = universel.jitter_plan((256, 144), (384, 216), "auto")
        self.assertEqual(period, 18)   # Halton, 8 * 1.5^2
        self.assertTrue(all(abs(c) <= 0.5 for f in range(18)
                            for c in jit(f)))

    def test_aucun(self):
        jit, period = universel.jitter_plan(RS, DS, "aucun")
        self.assertEqual((jit(5), period), ((0.0, 0.0), 0))


class Accumulation(unittest.TestCase):
    def test_sans_information_nouvelle_pas_de_derive(self):
        """Image fixe, pas de jitter : rien a accumuler, la sortie reste
        l'image de la premiere image (pas d'accentuation parasite)."""
        img = texture(*RS)
        up = universel.UniversalUpscaler(RS, DS)
        first = up.dispatch(img)
        for _ in range(6):
            last = up.dispatch(img)
        self.assertGreater(emul.psnr_display(last, first), 45.0)

    def test_jitter_fixe_converge(self):
        """Scene immobile echantillonnee en grille 2x2 : la sortie converge
        vers la scene a la resolution d'affichage, bien au-dela de
        l'agrandissement spatial."""
        game = emul.EmulatedGame(RealisticScene(seed=5, static=True),
                                 with_hud=False)
        jit, period = universel.jitter_plan(RS, DS, "grille")
        up = universel.UniversalUpscaler(RS, DS, period=period)
        for f in range(12):
            j = jit(f)
            img, _, _ = game.frame(0.0, RS, j, lod_bias=-1.0)
            out = up.dispatch(img, j)
        gt = game.truth(0.0, DS, ss=3)
        plain, _, _ = game.frame(0.0, RS)
        spatial = universel.lanczos_upscale(plain, DS)
        self.assertGreater(emul.psnr_display(out, gt),
                           emul.psnr_display(spatial, gt) + 1.0)

    def test_remise_a_zero(self):
        img = texture(*RS)
        up = universel.UniversalUpscaler(RS, DS)
        a = up.dispatch(img)
        up.dispatch(texture(*RS, dx=1.0))
        b = up.dispatch(img, reset=True)
        np.testing.assert_array_equal(a, b)

    def test_banc_format(self):
        """Fichiers du banc de bout en bout : en-tete et taille exacts."""
        import tempfile
        imgs = [np.full((4, 8, 3), 7, np.uint8)] * 2
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "e.bin")
            universel.write_banc_input(p, imgs, [(0.25, -0.25)] * 2, (8, 4),
                                       (16, 8), 4)
            data = np.fromfile(p, "<u4")
            self.assertEqual(int(data[0]), universel.BANC_MAGIC)
            self.assertEqual(list(data[1:7]), [8, 4, 16, 8, 2, 4])
            self.assertEqual(os.path.getsize(p), 32 + 2 * (8 + 8 * 4 * 4))


if __name__ == "__main__":
    unittest.main()
