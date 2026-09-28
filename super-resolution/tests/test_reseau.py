"""Le reseau : retropropagation, serialisation, export C++."""

import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from usr_ref.network import N_PADDED, N_PARAMS, Network  # noqa: E402
from usr_ref.train import Trainer, baseline_loss  # noqa: E402


def _batch(rng, n=64):
    return {"x": rng.normal(size=(n, 10)), "c": rng.uniform(size=(n, 3)),
            "hr": rng.uniform(size=(n, 3)), "hc": rng.uniform(size=(n, 3)),
            "ah": rng.uniform(0.05, 0.9, n), "g": rng.uniform(size=(n, 3)),
            "dg": rng.normal(0, 0.05, (n, 3))}


def _random_net(rng):
    return Network(rng.normal(0, .3, (16, 10)), rng.normal(0, .1, 16),
                   rng.normal(0, .3, (16, 16)), rng.normal(0, .1, 16),
                   rng.normal(0, .3, (2, 16)), rng.normal(0, .1, 2))


class Retropropagation(unittest.TestCase):
    def test_gradients_exacts(self):
        rng = np.random.default_rng(1)
        batch = _batch(rng)
        t = Trainer(rng, stability=0.7)
        t.p["w3"] = rng.normal(0, 0.5, (2, 16))
        t.p["b1"] = rng.normal(0, 0.1, 16)
        _, grads = t.loss_and_grads(batch)
        for k, v in t.p.items():
            for i in range(min(v.size, 12)):
                idx = np.unravel_index(i, v.shape)
                old = v[idx]
                v[idx] = old + 1e-6
                lp, _ = t.loss_and_grads(batch)
                v[idx] = old - 1e-6
                lm, _ = t.loss_and_grads(batch)
                v[idx] = old
                num = (lp - lm) / 2e-6
                self.assertAlmostEqual(num, grads[k][idx], delta=1e-6 + 1e-4
                                       * abs(num), msg="%s%s" % (k, idx))

    def test_normalisation_repliee(self):
        rng = np.random.default_rng(2)
        mean, std = rng.normal(size=10), rng.uniform(0.5, 2, 10)
        t = Trainer(rng, mean, std)
        t.p["w3"] = rng.normal(0, 0.5, (2, 16))
        x = rng.normal(size=(20, 10))
        p = t.p
        h1 = np.maximum(((x - mean) / std) @ p["w1"].T + p["b1"], 0)
        h2 = np.maximum(h1 @ p["w2"].T + p["b2"], 0)
        expected = h2 @ p["w3"].T + p["b3"]
        np.testing.assert_allclose(t.export().forward(x), expected,
                                   rtol=1e-4, atol=1e-5)

    def test_l_entrainement_fait_baisser_la_perte(self):
        rng = np.random.default_rng(3)
        n = 4000
        data = _batch(rng, n)
        # cas ou la bonne reponse depend d'une entree : si x0 > 0 la verite
        # est l'image courante, sinon l'historique brut
        data["g"] = np.where(data["x"][:, :1] > 0, data["c"], data["hr"])
        data["dg"] = data["g"] - data["hr"]
        t = Trainer(rng, stability=0.0)
        before, _ = t.loss_and_grads(data)
        for _ in range(300):
            idx = rng.integers(0, n, 512)
            _, g = t.loss_and_grads({k: v[idx] for k, v in data.items()})
            t.adam(g, 1e-2)
        after, _ = t.loss_and_grads(data)
        self.assertLess(after, 0.5 * before)
        self.assertGreater(baseline_loss(data, 0.0), 0.0)


class Serialisation(unittest.TestCase):
    def test_json_et_bin(self):
        net = _random_net(np.random.default_rng(4))
        x = np.random.default_rng(5).normal(size=(7, 10))
        with tempfile.TemporaryDirectory() as d:
            net.save(os.path.join(d, "n.json"), os.path.join(d, "n.bin"))
            self.assertEqual(os.path.getsize(os.path.join(d, "n.bin")),
                             N_PADDED * 4)
            for name in ("n.json", "n.bin"):
                back = Network.load(os.path.join(d, name))
                np.testing.assert_allclose(back.forward(x), net.forward(x),
                                           rtol=1e-6)

    def test_en_tete_cpp(self):
        net = _random_net(np.random.default_rng(6))
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "w.h")
            net.to_c_header(path)
            text = open(path).read()
            values = re.findall(r"(-?\d\.\d+e[+-]\d+)f", text)
            self.assertEqual(len(values), N_PADDED)
            np.testing.assert_allclose(np.array(values, np.float32),
                                       net.flat(), rtol=1e-6)
            cxx = shutil.which("g++") or shutil.which("clang++")
            if cxx:
                src = os.path.join(d, "t.cpp")
                with open(src, "w") as f:
                    f.write('#include "w.h"\nint main(){return '
                            'usr::detail::kDefaultWeights[0] > 1e30f;}\n')
                r = subprocess.run([cxx, "-std=c++17", "-Wall", "-Werror",
                                    "-fsyntax-only", "-I", d, src],
                                   capture_output=True, text=True)
                self.assertEqual(r.returncode, 0, r.stderr)

    def test_taille(self):
        self.assertEqual(N_PARAMS, 482)
        self.assertEqual(N_PADDED, 484)


if __name__ == "__main__":
    unittest.main()
