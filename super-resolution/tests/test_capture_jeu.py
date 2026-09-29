"""Captures de vrais jeux (usr_ref/capture_jeu.py) : le format ecrit par
Xenia (variable usr_capture), et la decimation qui en tire les sequences
d'entrainement. Sans Xenia : la capture est simulee avec le jeu emule rendu
a l'echelle 3."""

import os
import sys
import tempfile
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from usr_ref import capture_jeu, emul, train_universel, universel  # noqa: E402
from usr_ref.scene import Scene  # noqa: E402

DS = (384, 216)
RS = (128, 72)


class Capture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp()
        # Scene sans textures filtrees : le choix des mip-maps (qui differe
        # entre l'echelle 3 et l'echelle 1) n'y change rien.
        cls.game = emul.EmulatedGame(Scene(seed=5))
        cls.frames = [cls.game.frame(float(f), DS)[0] for f in range(10)]
        cls.path = os.path.join(cls.dir, "usrc_4D5307E6_1_00.bin")
        capture_jeu.ecrire(cls.path, cls.frames, crop=(6, 3))

    def test_en_tete_et_images(self):
        header, frames = capture_jeu.lire(self.path)
        self.assertEqual((header["largeur"], header["hauteur"]), DS)
        self.assertEqual(header["echelle"], (3, 3))
        self.assertEqual(header["decoupe"], (6, 3))
        self.assertEqual(header["images"], 10)
        # 10 bits par canal : l'image 8 bits du jeu emule revient a
        # l'arrondi pres
        for a, b in zip(frames, self.frames):
            self.assertLess(float(np.abs(a - b).max()), 0.5 / 1023 + 1e-6)

    def test_decimation_egale_rendu_decale(self):
        """Le coeur du protocole : la phase (i, j) de l'image a l'echelle 3
        est l'image que le jeu rendrait a l'echelle 1 avec le jitter de la
        grille 3x3 -- dans l'ordre exact de universel.GRID_ORDER."""
        _, frames = capture_jeu.lire(self.path)
        seq = capture_jeu.sequence(frames, 2)
        self.assertEqual(seq["rsize"], RS)
        self.assertEqual(seq["period"], 9)
        jit, period = universel.jitter_plan(RS, DS, "grille")
        self.assertEqual(period, 9)
        for f, (img, j, _) in enumerate(seq["items"]):
            self.assertEqual(tuple(np.float32(x) for x in jit(f)), j)
            ref, _, _ = self.game.frame(float(f), RS, jit(f),
                                        hud_jitter=True)
            self.assertLess(float(np.abs(img - ref).max()), 1e-3,
                            "image %d" % f)
            np.testing.assert_array_equal(seq["gt"][f], frames[f])

    def test_niveau1_phase_du_centre(self):
        _, frames = capture_jeu.lire(self.path)
        seq = capture_jeu.sequence(frames, 1)
        self.assertEqual(seq["period"], 0)
        for f, (img, j, _) in enumerate(seq["items"]):
            self.assertEqual(j, (0.0, 0.0))
            ref, _, _ = self.game.frame(float(f), RS)
            self.assertLess(float(np.abs(img - ref).max()), 1e-3)

    def test_sequence_interrompue(self):
        """Xenia arrete en pleine sequence : les images completes restent."""
        cut = os.path.join(self.dir, "usrc_coupee.bin")
        with open(self.path, "rb") as f:
            data = f.read()
        with open(cut, "wb") as f:
            f.write(data[:40 + 3 * DS[0] * DS[1] * 4 + 1000])
        header, frames = capture_jeu.lire(cut)
        self.assertEqual(header["images"], 3)
        self.assertEqual(header["images_prevues"], 10)
        os.remove(cut)

    def test_refuse_un_autre_fichier(self):
        other = os.path.join(self.dir, "autre.bin")
        np.arange(20, dtype="<u4").tofile(other)
        with self.assertRaises(ValueError):
            capture_jeu.lire(other)

    def test_entrainement_les_prend(self):
        seqs = train_universel.capture_sequences(self.dir, log=lambda m: None)
        self.assertEqual(len(seqs), 2)   # niveaux 1 et 2
        self.assertEqual({s["period"] for s in seqs}, {0, 9})

    def test_reserve_jamais_apprise(self):
        d = tempfile.mkdtemp()
        for k in range(9):
            capture_jeu.ecrire(os.path.join(d, "usrc_X_%d_%02d.bin" % (k, k)),
                               self.frames[:2])
        mesure = capture_jeu.fichiers(d, "mesure")
        appris = capture_jeu.fichiers(d, "entrainement")
        self.assertEqual(len(mesure), 2)
        self.assertEqual(len(appris), 7)
        self.assertFalse(set(mesure) & set(appris))
        # trop peu de captures : pas de reserve (et la commande le dit)
        self.assertEqual(capture_jeu.fichiers(self.dir, "mesure"),
                         capture_jeu.fichiers(self.dir, "entrainement"))

    def test_mesure(self):
        rows = capture_jeu.mesurer(self.dir, None, log=lambda m: None,
                                   warm=4)
        methods = {(r["niveau"], r["methode"]) for r in rows}
        self.assertIn((2, "USR-U regles"), methods)
        self.assertIn((1, "lanczos"), methods)
        for r in rows:
            self.assertTrue(np.isfinite(r["psnr"]))


if __name__ == "__main__":
    unittest.main()
