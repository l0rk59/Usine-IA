"""USR Labo : les shaders du laboratoire (scene, verite terrain,
agrandissements, composition de l'ecran) calculent-ils ce que calcule la
reference Python ? Et les ressources generees sont-elles a jour ?
"""

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

from usr_ref import core, evaluate, gpu, labo  # noqa: E402
from usr_ref.network import Network  # noqa: E402

_RUNNER = None


def _runner():
    global _RUNNER
    if _RUNNER is None:
        _RUNNER = gpu.ShaderRunner()
    return _RUNNER


def _vulkan_ok():
    if not gpu.available():
        return False
    try:
        _runner()
    except Exception:
        return False
    return True


def _scene_cbuffer(scene, t, t_prev=None):
    consts = labo.scene_constants(scene, t, t_prev)
    objs = consts.pop("objects")
    while len(objs) < labo.MAX_OBJECTS:
        objs.append({"centers": [0, 0, 0, 0], "shape": [1, 0, 0, 0],
                     "tint": [0, 0, 0, 0]})
    consts["g_Objects"] = objs
    return consts


class Ressources(unittest.TestCase):
    """Les en-tetes generes correspondent a leur source Python."""

    def test_police(self):
        cps, words = labo.read_font_header()
        self.assertEqual(cps, sorted(cps))
        self.assertEqual(cps[0], 32)                 # glyphe 0 = espace
        for ch in "Réglages «IA» àâçéèêëîïôùûœ ◀▶►●✓":
            self.assertIn(ord(ch), cps, ch)
        per_glyph = labo.GLYPH_H * labo.WORDS_PER_ROW
        self.assertEqual(len(words), len(cps) * per_glyph)
        self.assertTrue(np.all(words[:per_glyph] == 0))   # espace vide
        a = cps.index(ord("A"))
        self.assertGreater(int(np.count_nonzero(
            words[a * per_glyph:(a + 1) * per_glyph])), 10)

    def test_scene(self):
        with open(os.path.join(labo.SRC, "labo_scene_params.h")) as f:
            text = f.read()
        scene = labo.labo_scene()
        cam0 = re.search(r"kCam0\[2\] = \{([^}]*)\}", text).group(1)
        np.testing.assert_allclose([float(x) for x in cam0.split(",")],
                                   scene.cam0, rtol=1e-15)
        self.assertIn("kObjectCount = %d" % len(scene.objects), text)

    def test_modeles(self):
        with open(os.path.join(labo.SRC, "labo_models.h")) as f:
            text = f.read()
        for name, filename in labo.MODELS:
            block = re.search(r"k_%s\[484\] = \{(.*?)\};" % name, text, re.S)
            values = np.array(re.findall(r"(-?\d\.\d+e[+-]\d+)f",
                                         block.group(1)), np.float32)
            net = Network.load(os.path.join(ROOT, "weights", filename))
            np.testing.assert_allclose(values, net.flat(), rtol=1e-6)

    def test_icones_uwp(self):
        for name, (w, h) in labo.ICONS.items():
            path = os.path.join(labo.LABO, "uwp", "Assets", name)
            with open(path, "rb") as f:
                head = f.read(24)
            self.assertEqual(head[:8], b"\x89PNG\r\n\x1a\n", name)
            self.assertEqual(int.from_bytes(head[16:20], "big"), w, name)
            self.assertEqual(int.from_bytes(head[20:24], "big"), h, name)


_CXX = shutil.which("g++") or shutil.which("clang++")


@unittest.skipUnless(_CXX, "compilateur C++ absent")
class CoeurCpp(unittest.TestCase):
    """Le coeur C++ du Labo (menu, reglages, scene) compile en -Werror,
    passe ses tests, et anime la scene comme la reference Python."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.exe = os.path.join(cls.tmp, "test_labo_core")
        src = os.path.join(labo.LABO, "src")
        r = subprocess.run(
            [_CXX, "-std=c++17", "-Wall", "-Wextra", "-Werror", "-O1",
             "-I", src, os.path.join(src, "labo_core.cpp"),
             os.path.join(src, "labo_text.cpp"),
             os.path.join(labo.LABO, "tests", "test_labo_core.cpp"),
             "-o", cls.exe], capture_output=True, text=True)
        cls.build_error = r.stderr if r.returncode else None

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_compile_et_passe(self):
        self.assertIsNone(self.build_error, self.build_error)
        r = subprocess.run([self.exe], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("0 echec", r.stdout)

    def test_scene_egale_python(self):
        self.assertIsNone(self.build_error, self.build_error)
        times = [0.0, 1.0, 12.5, 250.0, 1234.25]
        r = subprocess.run([self.exe, "--scene"] + [str(t) for t in times],
                           capture_output=True, text=True, check=True)
        scene = labo.labo_scene()
        for t, line in zip(times, r.stdout.splitlines()):
            got = [float(x) for x in line.split()]
            c = labo.scene_constants(scene, t)
            expected = c["g_Camera"] + [c["g_Aspect"], c["g_ScreenPhase"],
                                        c["g_NeonOn"], c["g_ObjectCount"]]
            for o in c["objects"]:
                expected += o["centers"] + o["shape"] + o["tint"][:3]
            np.testing.assert_allclose(got, expected, rtol=1e-6, atol=1e-6,
                                       err_msg="t=%s" % t)


@unittest.skipUnless(_vulkan_ok(), "slangpy ou Vulkan indisponible")
class ShadersLabo(unittest.TestCase):
    def test_scene_egale_reference(self):
        import slangpy as spy
        run = _runner()
        scene = labo.labo_scene()
        w, h = 80, 45
        for t, jitter in ((0.0, (0.0, 0.0)), (37.0, (0.3125, -0.2)),
                          (250.0, (-0.45, 0.4))):
            col = run.texture("rgba16_float", w, h)
            dep = run.texture("r32_float", w, h)
            mot = run.texture("rg16_float", w, h)
            run.run("labo_scene", (w, h), {
                "LaboScenePass": {"g_Size": spy.uint2(w, h),
                                  "g_Jitter": list(jitter)},
                "LaboScene": _scene_cbuffer(scene, t)},
                {"u_Color": col, "u_Depth": dep, "u_Motion": mot})
            rc, rz, rm = scene.render(t, (w, h), jitter)
            gc = col.to_numpy()[..., :3].astype(np.float32)
            diff = np.abs(gc - rc).max(-1)
            # le GPU calcule en float32 : aux frontieres exactes d'un motif,
            # un pixel peut basculer. Ailleurs, arrondi FP16 du stockage.
            self.assertLess(float(np.mean(diff > 0.01)), 0.01, t)
            self.assertLess(float(np.median(diff)), 2e-3, t)
            np.testing.assert_allclose(dep.to_numpy(), rz, rtol=1e-6)
            mv = mot.to_numpy().astype(np.float32) / np.array([w, h])
            self.assertLess(float(np.mean(np.abs(mv - rm) > 1e-4)), 0.01)

    def test_verite_terrain(self):
        import slangpy as spy
        run = _runner()
        scene = labo.labo_scene()
        w, h = 64, 36
        out = run.texture("rgba16_float", w, h)
        run.run("labo_truth", (w, h), {
            "LaboTruthPass": {"g_Size": spy.uint2(w, h), "g_Samples": 4},
            "LaboScene": _scene_cbuffer(scene, 20.0)}, {"u_Truth": out})
        gpu_img = out.to_numpy()[..., :3].astype(np.float32)
        self.assertGreater(evaluate.psnr(gpu_img,
                                         scene.ground_truth(20.0, (w, h))),
                           45.0)

    def test_agrandissements(self):
        import slangpy as spy
        run = _runner()
        rng = np.random.default_rng(0)
        src_np = rng.uniform(0, 2, (18, 32, 4)).astype(np.float32)
        src = run.texture("rgba32_float", 32, 18, src_np)
        dst = run.texture("rgba32_float", 96, 54)
        consts = {"g_SrcSize": spy.uint2(32, 18),
                  "g_DstSize": spy.uint2(96, 54)}
        run.run("labo_upscale", (96, 54),
                {"LaboUpscalePass": dict(consts, g_Mode=0)},
                {"t_Source": src, "u_Dest": dst})
        np.testing.assert_allclose(
            dst.to_numpy()[..., :3],
            evaluate.bilinear_upscale(src_np[..., :3], (96, 54)), atol=1e-5)
        run.run("labo_upscale", (96, 54),
                {"LaboUpscalePass": dict(consts, g_Mode=1)},
                {"t_Source": src, "u_Dest": dst})
        np.testing.assert_array_equal(
            dst.to_numpy(), np.repeat(np.repeat(src_np, 3, 0), 3, 1))

    def test_composition(self):
        import slangpy as spy
        run = _runner()
        rng = np.random.default_rng(1)
        w, h = 120, 72
        left = rng.uniform(0, 3, (h, w, 4)).astype(np.float32)
        right = rng.uniform(0, 1, (h, w, 4)).astype(np.float32)
        debug = rng.uniform(0, 1, (h, w, 4)).astype(np.float32)
        motion = rng.normal(0, 3, (24, 40, 2)).astype(np.float32)
        cps, font = labo.read_font_header()
        cols, rows = w // 12, h // 24
        text = np.zeros(cols * rows, np.uint32)
        for i, ch in enumerate("Réglé ◀▶"):
            text[cols + 1 + i] = cps.index(ord(ch)) | (2 << 12)
        text[2 * cols:2 * cols + 5] |= labo.CELL_PANEL
        text[3] |= labo.CELL_HIGHLIGHT
        t_left = run.texture("rgba32_float", w, h, left)
        t_right = run.texture("rgba32_float", w, h, right)
        t_debug = run.texture("rgba32_float", w, h, debug)
        t_motion = run.texture("rg32_float", 40, 24, motion)
        out = run.texture("rgba8_unorm", w, h)
        for lv, rv, zoom in ((0, 0, 3.0), (1, 5, 0.0), (2, 3, 2.0),
                             (4, 0, 0.0)):
            c = {"OutSize": (w, h), "TextGrid": (cols, rows),
                 "CellSize": (12, 24), "GlyphSize": (12, 24),
                 "MotionSize": (40, 24), "ZoomCenter": (70.0, 30.0),
                 "SplitX": 55, "LeftView": lv, "RightView": rv,
                 "ZoomFactor": zoom, "ZoomRadius": 20.0, "MotionScale": 4.0}
            cb = {"g_" + k: (spy.uint2(*v) if k in ("OutSize", "TextGrid",
                                                    "CellSize", "GlyphSize",
                                                    "MotionSize") else v)
                  for k, v in c.items()}
            run.run("labo_compose", (w, h), {"LaboComposePass": cb}, {
                "t_Left": t_left, "t_Right": t_right, "t_Debug": t_debug,
                "t_Motion": t_motion, "t_Font": run.buffer(font),
                "t_Text": run.buffer(text), "u_Out": out})
            got = out.to_numpy()[..., :3].astype(np.float32)
            ref = labo.compose_reference(c, left[..., :3], right[..., :3],
                                         debug, motion, font, text)
            ref8 = np.round(np.clip(ref, 0, 1) * 255.0)
            diff = np.abs(got - ref8)
            self.assertLessEqual(float(np.percentile(diff, 99.5)), 1.0,
                                 (lv, rv, zoom))
            self.assertLess(float(np.mean(diff > 2)), 0.002, (lv, rv, zoom))


if __name__ == "__main__":
    unittest.main()
