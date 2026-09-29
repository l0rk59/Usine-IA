"""Verification de bout en bout de USR Universel : la bibliotheque C++
elle-meme (usr::UniversalContext), en Direct3D 12.

``tests/wine/universel_wine.sh`` compile la bibliotheque et un petit
programme (tests/wine/usr_universal_run.cpp) avec MinGW, les execute sous
Wine avec vkd3d-proton sur un GPU logiciel, sur la sequence ecrite par
``python -m usr_ref universel-entree`` (jeu emule, jitter en grille, HUD
fixe, remise a zero a l'image 12). Ce test rejoue la meme sequence dans la
reference Python et exige la meme image : il valide tout le chemin reel
(9 passes, descripteurs, barrieres, anneau des images precedentes,
constantes, poids).

Active si USR_UNIVERSEL_SORTIE designe la sortie du programme ; les poids
utilises sont dans USR_UNIVERSEL_POIDS (.json) ou, a defaut, ceux livres.
"""

import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from usr_ref import emul, interpolation, universel  # noqa: E402
from usr_ref.network import Network  # noqa: E402

SORTIE = os.environ.get("USR_UNIVERSEL_SORTIE", "")
POIDS = os.environ.get("USR_UNIVERSEL_POIDS", "")
IMAGES = int(os.environ.get("USR_UNIVERSEL_IMAGES", "16"))


def _weights():
    if POIDS:
        return Network.load(POIDS)
    path = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "weights", "usr_universel.json")
    return Network.load(path) if os.path.exists(path) else None


@unittest.skipUnless(SORTIE and os.path.exists(SORTIE),
                     "USR_UNIVERSEL_SORTIE non defini (voir "
                     "tests/wine/universel_wine.sh)")
class BibliothequeUniverselle(unittest.TestCase):
    def test_meme_image_que_la_reference(self):
        images, jitters, period = universel.banc_sequence(IMAGES)
        flows = []
        ref = universel.banc_reference(images, jitters, (192, 108),
                                       (384, 216), period, _weights(),
                                       flows=flows)
        app, mids = universel.read_banc_output(SORTIE, (384, 216), IMAGES,
                                               generation=True)
        for f in range(IMAGES):
            out = np.clip(app[f], 0.0, 1.0)
            self.assertTrue(np.all(np.isfinite(app[f])), "image %d" % f)
            self.assertGreater(emul.psnr_display(out, ref[f]), 55.0,
                               "image %d" % f)
            if flows[f] is None:
                # pas de flot : la bibliotheque refuse (NotReady), le banc
                # recopie la sortie
                np.testing.assert_array_equal(mids[f], app[f])
                continue
            # Memes images d'entree que la bibliotheque (les siennes) : seule
            # la generation est jugee ici. Sorties stockees en 16 bits.
            prev = np.clip(app[f - 1], 0.0, 1.0)
            want, _, _ = interpolation.interpoler(prev, out, flows[f],
                                                  flows[f - 1])
            self.assertGreater(emul.psnr_display(mids[f], want), 50.0,
                               "image generee %d" % f)


if __name__ == "__main__":
    unittest.main()
