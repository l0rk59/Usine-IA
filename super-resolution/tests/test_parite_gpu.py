"""Les shaders HLSL, executes sur un GPU via Vulkan, donnent-ils la meme
image que la reference NumPy ? C'est la preuve que ce qui a ete mis au
point et entraine en Python est bien ce qui tournera sur la console.

Necessite ``pip install slangpy`` et un pilote Vulkan (sans carte
graphique : ``apt install mesa-vulkan-drivers`` fournit llvmpipe).
"""

import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from usr_ref import core, evaluate, gpu  # noqa: E402
from usr_ref.network import Network, load_default  # noqa: E402
from usr_ref.scene import Scene  # noqa: E402

def _device():
    return gpu.shared_device()


def _vulkan_ok():
    if not gpu.available():
        return False
    try:
        _device()
    except Exception:
        return False
    return True


@unittest.skipUnless(_vulkan_ok(), "slangpy ou Vulkan indisponible")
class PariteGpu(unittest.TestCase):
    SIZE = (96, 54)

    def _compare(self, network, mode, frames=6, sharpness=0.5, min_db=55.0,
                 **settings):
        rsize = core.render_size(self.SIZE, mode)
        phases = core.jitter_phase_count(rsize[0], self.SIZE[0])
        scene = Scene(seed=3)
        g = gpu.GpuUpscaler(rsize, self.SIZE, network=network,
                            device=_device(), **settings)
        r = core.Upscaler(rsize, self.SIZE, network=network, **settings)
        for f in range(frames):
            j = core.jitter_offset(f, phases)
            color, invz, motion = scene.render(f, rsize, j)
            out_gpu = g.dispatch(color, invz, motion, j, sharpness=sharpness)
            out_ref, info = r.dispatch(color, invz, motion, j,
                                       sharpness=sharpness,
                                       return_internals=True)
            self.assertGreater(evaluate.psnr(out_gpu, out_ref), min_db,
                               "image %d" % f)
            # sortie de diagnostic (alpha, beta, confiance, desocclusion)
            self.assertLess(float(np.mean(np.abs(g.read_debug()
                                                 - info["debug"]))), 0.01)
            if f == 0:
                # passe 1 : exacte (aucun arrondi en jeu hors stockage)
                mv, invz_gpu, dis = g.read_intermediates()
                np.testing.assert_array_equal(invz_gpu, r.prev_invz)
        # Confiance (0..10, en FP16). Dans les aplats parfaits, les entrees
        # du reseau sont des rapports de differences au niveau de l'arrondi
        # FP16 : le compteur peut y diverger sur quelques pixels, sans effet
        # visible (tout y a la meme couleur). On exige l'accord partout
        # ailleurs, et l'image est deja verifiee a > 55 dB ci-dessus.
        hist_gpu = g.read_history()
        diff = np.abs(hist_gpu[..., 3] - r.history[..., 3])
        self.assertGreater(np.mean(diff < 0.25), 0.99)
        self.assertLess(float(diff.mean()), 0.05)
        np.testing.assert_allclose(hist_gpu[..., :3], r.history[..., :3],
                                   atol=0.02)

    def test_heuristique(self):
        self._compare(None, "performance")

    def test_reseau_aleatoire(self):
        rng = np.random.default_rng(0)
        net = Network(rng.normal(0, .3, (16, 10)), rng.normal(0, .1, 16),
                      rng.normal(0, .3, (16, 16)), rng.normal(0, .1, 16),
                      rng.normal(0, .3, (2, 16)), [0.2, -1.0])
        self._compare(net, "qualite")

    @unittest.skipIf(load_default() is None, "poids absents")
    def test_reseau_livre(self):
        self._compare(load_default(), "performance", frames=8)

    @unittest.skipIf(load_default() is None, "poids absents")
    def test_reglages_extremes(self):
        self._compare(load_default(), "ultra", net_strength=2.5,
                      max_count=32.0, clip_gamma=4.0, kernel_width=0.5)
        self._compare(load_default(), "natif", net_strength=0.3,
                      max_count=2.0, clip_gamma=0.5, kernel_width=2.0)


if __name__ == "__main__":
    unittest.main()
