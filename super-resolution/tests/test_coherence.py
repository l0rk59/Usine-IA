"""Les trois implementations (NumPy, HLSL, C++) doivent partager les memes
constantes et le meme format de poids. Et les shaders doivent compiler.

Compilation des shaders : si ``dxc`` est dans le PATH (ou USR_DXC).
Compilation C++ : si USR_DIRECTX_HEADERS pointe vers un clone de
https://github.com/microsoft/DirectX-Headers (verification sous Linux).
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

from usr_ref import core, network  # noqa: E402

SHADERS = os.path.join(ROOT, "shaders")
PASSES = ("usr_prepare", "usr_accumulate", "usr_sharpen")
# USR Universel (sans vecteurs de mouvement)
UPASSES = ("usr_u_luma", "usr_u_down", "usr_u_grad", "usr_u_flow",
           "usr_u_median", "usr_u_finalize", "usr_u_residual",
           "usr_u_accumulate", "usr_u_output")
LABO_PASSES = ("labo_scene", "labo_truth", "labo_upscale", "labo_compose",
               "labo_encode")


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def _hlsl_const(text, name):
    m = re.search(r"static const (?:float|int|uint)\s+%s\s*=\s*([-\d.eE+]+)"
                  % name, text)
    return float(m.group(1))


def _dxc():
    return os.environ.get("USR_DXC") or shutil.which("dxc")


class Constantes(unittest.TestCase):
    def test_hlsl_egal_numpy(self):
        text = _read("shaders", "usr_common.hlsli")
        pairs = {"USR_SIGMA_FRESH": core.SIGMA_FRESH,
                 "USR_KERNEL_COUNT": core.KERNEL_COUNT,
                 "USR_DISOCC_T0": core.DISOCC_T0,
                 "USR_DISOCC_T1": core.DISOCC_T1,
                 "USR_SHARPEN_PEAK": core.SHARPEN_PEAK,
                 "USR_EPS_SIGMA": core.EPS_SIGMA}
        for name, value in pairs.items():
            self.assertAlmostEqual(_hlsl_const(text, name), value, msg=name)
        self.assertIn("#define USR_FLAG_RESET   %du" % core.FLAG_RESET, text)
        self.assertIn("#define USR_FLAG_NETWORK %du" % core.FLAG_NETWORK,
                      text)
        self.assertIn("#define USR_FLAG_DEBUG   %du" % core.FLAG_DEBUG, text)

    def test_universel_hlsl_egal_numpy(self):
        from usr_ref import flow, universel
        text = _read("shaders", "usr_u_common.hlsli")
        pairs = {"USR_U_PATCH_R": flow.PATCH_R,
                 "USR_U_COST_SCALE": flow.COST_SCALE,
                 "USR_U_MEDIAN_SCALE": flow.MEDIAN_SCALE,
                 "USR_U_COARSE_RADIUS": flow.COARSE_RADIUS,
                 "USR_U_LAMBDA": flow.LAMBDA,
                 "USR_U_CONTRAST_FLOOR": flow.CONTRAST_FLOOR,
                 "USR_U_LK_MAX_STEP": flow.LK_MAX_STEP,
                 "USR_U_LK_COND": flow.LK_COND,
                 "USR_U_CONF_FLOOR": flow.CONF_FLOOR,
                 "USR_U_CONF_T0": flow.CONF_T0,
                 "USR_U_CONF_T1": flow.CONF_T1,
                 "USR_U_SIGMA_PROX": universel.SIGMA_PROX,
                 "USR_U_RANGE_EPS": universel.RANGE_EPS,
                 "USR_U_FEAT_EPS": universel.FEAT_EPS}
        for name, value in pairs.items():
            self.assertAlmostEqual(_hlsl_const(text, name), value, msg=name)
        cpp = _read("src", "usr_universal_dx12.cpp")
        self.assertIn("kMaxLevels = %d" % flow.MAX_LEVELS, cpp)
        self.assertIn("kMaxPeriod = %d" % flow.MAX_PERIOD, cpp)
        self.assertIn("kMinCoarseSide = %d" % flow.MIN_COARSE_SIDE, cpp)

    def test_cpp_egal_numpy(self):
        text = _read("src", "usr_dx12.cpp")
        header = _read("include", "usr", "usr.h")

        def cst(name, src=text):
            return float(re.search(r"%s = ([\d.]+)[fu]?;" % name,
                                   src).group(1))

        self.assertAlmostEqual(cst("kSigmaSharpDisplay"),
                               core.SIGMA_SHARP_DISPLAY)
        self.assertEqual(int(cst("kFlagReset")), core.FLAG_RESET)
        self.assertEqual(int(cst("kFlagNetwork")), core.FLAG_NETWORK)
        self.assertEqual(int(cst("kFlagDebug")), core.FLAG_DEBUG)
        self.assertEqual(int(cst("kWeightFloats")), network.N_PADDED)
        # valeurs par defaut de DispatchDesc = celles de l'entrainement
        self.assertAlmostEqual(cst("historyLength", header),
                               core.DEFAULT_MAX_COUNT)
        self.assertAlmostEqual(cst("antiGhosting", header),
                               core.DEFAULT_CLIP_GAMMA)
        self.assertAlmostEqual(cst("networkStrength", header), 1.0)
        self.assertAlmostEqual(cst("kernelWidth", header), 1.0)

    def test_disposition_des_poids(self):
        text = _read("shaders", "usr_network.hlsli")

        def define(name):
            return int(re.search(r"#define %s\s+(\d+)" % name, text).group(1))

        h, i, o = network.HIDDEN, core.N_FEATURES, network.OUTPUTS
        self.assertEqual(define("USR_NET_INPUTS"), i)
        self.assertEqual(define("USR_NET_HIDDEN"), h)
        self.assertEqual(define("USR_NET_B1"), h * i)
        self.assertEqual(define("USR_NET_W2"), h * i + h)
        self.assertEqual(define("USR_NET_B2"), h * i + h + h * h)
        self.assertEqual(define("USR_NET_W3"), h * i + 2 * h + h * h)
        self.assertEqual(define("USR_NET_B3"), h * i + 2 * h + h * h + o * h)
        self.assertIn("float4 g_Net[%d]" % (network.N_PADDED // 4), text)

    def test_20_constantes_racine(self):
        text = _read("shaders", "usr_common.hlsli")
        block = re.search(r"cbuffer USRConstants[^{]*\{(.*?)\};", text,
                          re.S).group(1)
        sizes = {"uint2": 2, "float2": 2, "float": 1, "uint": 1}
        total = sum(sizes[t] for t in re.findall(r"^\s*(\w+)\s+g_", block,
                                                  re.M))
        self.assertEqual(total, 20)
        self.assertIn("num32BitConstants=20", text)
        cpp = _read("src", "usr_dx12.cpp")
        self.assertIn("kRootConstantCount = 20", cpp)

    def test_poids_livres_coherents(self):
        path = network.default_weights_path()
        if not os.path.exists(path):
            self.skipTest("poids absents")
        net = network.Network.load(path)
        binary = network.Network.load(os.path.splitext(path)[0] + ".bin")
        self.assertTrue((net.flat() == binary.flat()).all())
        header = _read("src", "usr_default_weights.h")
        values = re.findall(r"(-?\d\.\d+e[+-]\d+)f", header)
        self.assertEqual(len(values), network.N_PADDED)
        self.assertAlmostEqual(float(values[0]), float(net.flat()[0]),
                               places=6)


    def test_poids_universels_coherents(self):
        path = os.path.join(ROOT, "weights", "usr_universel.json")
        if not os.path.exists(path):
            self.skipTest("poids absents")
        net = network.Network.load(path)
        binary = network.Network.load(os.path.splitext(path)[0] + ".bin")
        self.assertTrue((net.flat() == binary.flat()).all())
        header = _read("src", "usr_universal_weights.h")
        self.assertIn("exporter --universel", header)
        values = [float(v) for v in
                  re.findall(r"(-?\d\.\d+e[+-]\d+)f", header)]
        self.assertEqual(len(values), network.N_PADDED)
        np.testing.assert_allclose(values[:network.N_PARAMS],
                                   net.flat()[:network.N_PARAMS],
                                   rtol=1e-8, atol=0)


@unittest.skipUnless(_dxc(), "dxc absent")
class CompilationShaders(unittest.TestCase):
    def _compile(self, name, *extra, folder=SHADERS):
        with tempfile.TemporaryDirectory() as d:
            r = subprocess.run(
                [_dxc(), "-T", extra[0] if extra else "cs_6_0", "-E", "main",
                 "-O3", "-WX", *extra[1:], "-Fo", os.path.join(d, "o.bin"),
                 os.path.join(folder, name + ".hlsl")],
                capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, name + " : " + r.stderr)

    def test_dxil_sm60(self):
        for p in PASSES + UPASSES:
            self._compile(p, "cs_6_0")

    def test_dxil_sm62_fp16(self):
        for p in PASSES + UPASSES:
            self._compile(p, "cs_6_2", "-DUSR_NETWORK_HALF=1")

    def test_spirv(self):
        for p in PASSES + UPASSES:
            self._compile(p, "cs_6_0", "-spirv")

    def test_labo(self):
        for p in LABO_PASSES:
            self._compile(p, "cs_6_0",
                          folder=os.path.join(ROOT, "labo", "shaders"))


@unittest.skipUnless(os.environ.get("USR_DIRECTX_HEADERS") and _dxc() and
                     (shutil.which("g++") or shutil.which("clang++")),
                     "USR_DIRECTX_HEADERS, dxc ou compilateur C++ absent")
class CompilationCpp(unittest.TestCase):
    def test_bibliotheque_compile(self):
        dxh = os.path.join(os.environ["USR_DIRECTX_HEADERS"], "include")
        cxx = shutil.which("g++") or shutil.which("clang++")
        with tempfile.TemporaryDirectory() as gen:
            for header, passes in (("usr_shaders.h", PASSES),
                                   ("usr_universal_shaders.h", UPASSES)):
                with open(os.path.join(gen, header), "w") as f:
                    for p in passes:
                        subprocess.run(
                            [_dxc(), "-T", "cs_6_0", "-E", "main", "-O3",
                             "-Fh", os.path.join(gen, p + ".h"),
                             "-Vn", "g_" + p,
                             os.path.join(SHADERS, p + ".hlsl")],
                            check=True, capture_output=True)
                        f.write('#include "%s.h"\n' % p)
            for source in ("usr_dx12.cpp", "usr_universal_dx12.cpp"):
                r = subprocess.run(
                    [cxx, "-std=c++17", "-Wall", "-Wextra", "-Werror",
                     "-fsyntax-only", "-include", "wsl/winadapter.h",
                     "-include", "directx/d3d12.h",
                     "-include", "dxguids/dxguids.h",
                     "-I", os.path.join(ROOT, "include"),
                     "-I", os.path.join(ROOT, "src"), "-I", gen, "-I", dxh,
                     "-I", os.path.join(dxh, "directx"),
                     "-I", os.path.join(dxh, "wsl", "stubs"),
                     os.path.join(ROOT, "src", source)],
                    capture_output=True, text=True)
                self.assertEqual(r.returncode, 0, source + " : " + r.stderr)


if __name__ == "__main__":
    unittest.main()
