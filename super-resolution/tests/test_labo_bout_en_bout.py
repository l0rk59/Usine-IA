"""Verification de bout en bout : l'application Windows elle-meme.

``labo/tests/capture_wine.sh`` compile usr_labo.exe (bibliotheque C++
Direct3D 12 + Labo), l'execute sous Wine avec vkd3d-proton sur un GPU
logiciel, et enregistre, image par image, les entrees de USR (couleur,
profondeur, mouvement produits par le shader de scene) et sa sortie.

Ce test rejoue ces entrees dans la reference Python et exige la meme
image : il valide tout le chemin reel (signature racine lue dans le
bytecode, descripteurs, barrieres, 20 constantes racine, poids, sortie).

Active si USR_LABO_CAPTURES designe le dossier des captures.
"""

import glob
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from usr_ref import core, evaluate, labo  # noqa: E402
from usr_ref.network import load_default  # noqa: E402

CAPTURES = os.environ.get("USR_LABO_CAPTURES", "")


@unittest.skipUnless(CAPTURES and glob.glob(os.path.join(CAPTURES,
                                                         "frame_*.bin")),
                     "USR_LABO_CAPTURES non defini (voir capture_wine.sh)")
class ApplicationWindows(unittest.TestCase):
    def setUp(self):
        self.paths = sorted(glob.glob(os.path.join(CAPTURES, "frame_*.bin")))

    def test_format(self):
        cap = labo.read_capture(self.paths[0])
        dw, dh = cap["display"]
        rw, rh = cap["render"]
        self.assertEqual((rw, rh), core.render_size((dw, dh), "performance"))
        self.assertTrue(np.all(np.isfinite(cap["usr"])))
        # la scene a bien ete rendue : profondeurs du decor et des objets
        self.assertAlmostEqual(float(cap["depth"].min()), 1 / 20.0, places=5)
        self.assertGreater(float(cap["depth"].max()), 0.1)

    def test_meme_image_que_la_reference(self):
        results = labo.replay_captures(self.paths, load_default())
        for i, (app, ref) in enumerate(results):
            self.assertGreater(evaluate.psnr(app, ref), 55.0, "image %d" % i)

    def test_capture_ecran(self):
        path = os.path.join(CAPTURES, "capture.png")
        self.assertTrue(os.path.exists(path))
        with open(path, "rb") as f:
            self.assertEqual(f.read(8), b"\x89PNG\r\n\x1a\n")


if __name__ == "__main__":
    unittest.main()
