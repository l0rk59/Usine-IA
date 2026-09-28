"""Execute les VRAIS shaders HLSL de ``shaders/`` sur un GPU (ou sur le
GPU logiciel ``llvmpipe`` de Mesa, sans carte graphique) via slangpy/Vulkan.

Sert au test de parite : les memes images passent dans la reference NumPy
et dans les shaders, et on compare. Seule transformation appliquee au
source : les ``#include`` sont deplies, les annotations ``register(...)``
et ``[RootSignature(...)]`` retirees -- elles sont propres a Direct3D 12
(sous Vulkan, b0, t0 et u0 deviendraient tous le binding 0). La logique
est intacte.

Dependance optionnelle : ``pip install slangpy`` (+ un pilote Vulkan).
"""

import os
import re

import numpy as np

from . import core

SHADER_DIR = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "shaders")

_INCLUDE = re.compile(r'^\s*#include\s+"([^"]+)"\s*$', re.M)
_REGISTER = re.compile(r":\s*register\s*\(\s*[a-z]\d+\s*\)")
_ROOTSIG = re.compile(r"^\s*\[RootSignature\([^)]*\)\]\s*$", re.M)


LABO_SHADER_DIR = os.path.join(os.path.dirname(SHADER_DIR), "labo",
                               "shaders")


def flatten_source(name, seen=None, directory=SHADER_DIR):
    seen = set() if seen is None else seen
    path = os.path.join(directory, name)
    with open(path, encoding="utf-8") as f:
        src = f.read()

    def expand(m):
        inc = m.group(1)
        if inc in seen:
            return ""
        seen.add(inc)
        return flatten_source(inc, seen, directory)

    return _ROOTSIG.sub("", _REGISTER.sub("", _INCLUDE.sub(expand, src)))


def _assign(parent, key, value, spy):
    """Ecrit recursivement une valeur Python dans un champ de shader.

    dict -> structure, liste de dict -> tableau de structures, liste de
    nombres -> floatN ; pour un vecteur entier, passer un type slangpy
    (spy.uint2...). Les scalaires Python passent tels quels.
    """
    if isinstance(value, dict):
        for k, v in value.items():
            _assign(parent[key], k, v, spy)
    elif isinstance(value, (list, tuple)) and value and isinstance(
            value[0], dict):
        for i, v in enumerate(value):
            _assign(parent[key], i, v, spy)
    elif isinstance(value, (list, tuple, np.ndarray)):
        vec = {2: spy.float2, 3: spy.float3, 4: spy.float4}[len(value)]
        parent[key] = vec(*[float(x) for x in value])
    else:
        parent[key] = value


class ShaderRunner:
    """Execute un shader compute quelconque de ``directory`` (Labo...)."""

    def __init__(self, directory=LABO_SHADER_DIR, device=None):
        import slangpy as spy
        self.spy = spy
        self.directory = directory
        self.dev = device or shared_device()
        self.kernels = {}

    def kernel(self, name):
        if name not in self.kernels:
            src = flatten_source(name + ".hlsl", directory=self.directory)
            path = os.path.join(self.directory, name + ".hlsl")
            mod = self.dev.load_module_from_source(name, src, path)
            prog = self.dev.link_program([mod], [mod.entry_point("main")])
            self.kernels[name] = self.dev.create_compute_kernel(prog)
        return self.kernels[name]

    def texture(self, fmt, w, h, data=None):
        spy = self.spy
        usage = (spy.TextureUsage.shader_resource
                 | spy.TextureUsage.unordered_access)
        kw = {"data": np.ascontiguousarray(data)} if data is not None else {}
        return self.dev.create_texture(format=getattr(spy.Format, fmt),
                                       width=w, height=h, usage=usage,
                                       mip_count=1, **kw)

    def buffer(self, data):
        spy = self.spy
        data = np.ascontiguousarray(data, np.uint32)
        return self.dev.create_buffer(
            element_count=len(data), struct_size=4,
            usage=spy.BufferUsage.shader_resource, data=data)

    def run(self, name, threads, cbuffers, resources):
        spy = self.spy
        enc = self.dev.create_command_encoder()
        with enc.begin_compute_pass() as cp:
            cur = spy.ShaderCursor(cp.bind_pipeline(
                self.kernel(name).pipeline))
            for block, values in cbuffers.items():
                _assign(cur, block, values, spy)
            for k, v in resources.items():
                cur[k] = v
            cp.dispatch([threads[0], threads[1], 1])
        self.dev.submit_command_buffer(enc.finish())
        self.dev.wait()


def available():
    try:
        import slangpy  # noqa: F401
    except Exception:
        return False
    return True


_SHARED_DEVICE = None


def shared_device():
    """Un seul peripherique Vulkan par processus : slangpy supporte mal
    plusieurs peripheriques simultanes (plantage au chargement des
    shaders quand deux suites de tests en creent chacune un)."""
    global _SHARED_DEVICE
    if _SHARED_DEVICE is None:
        import slangpy as spy
        _SHARED_DEVICE = spy.Device(type=spy.DeviceType.vulkan,
                                    enable_hot_reload=False)
    return _SHARED_DEVICE


class GpuUpscaler:
    """Meme interface que core.Upscaler, mais calcule par les shaders."""

    def __init__(self, render_size, display_size, network=None,
                 max_count=core.DEFAULT_MAX_COUNT,
                 clip_gamma=core.DEFAULT_CLIP_GAMMA, net_strength=1.0,
                 kernel_width=1.0, device=None):
        import slangpy as spy
        self.spy = spy
        self.dev = device or shared_device()
        self.render_size = render_size
        self.display_size = display_size
        self.network = network
        self.max_count = max_count
        self.clip_gamma = clip_gamma
        self.net_strength = net_strength
        self.kernel_width = kernel_width
        self.kernels = {n: self._kernel(n) for n in
                        ("usr_prepare", "usr_accumulate", "usr_sharpen")}

        rw, rh = render_size
        dw, dh = display_size
        F = spy.Format
        self.dilated_mv = self._tex(F.rg16_float, rw, rh)
        self.invz = [self._tex(F.r32_float, rw, rh) for _ in range(2)]
        self.disocc = self._tex(F.r8_unorm, rw, rh)
        self.history = [self._tex(F.rgba16_float, dw, dh) for _ in range(2)]
        self.output = self._tex(F.rgba16_float, dw, dh)
        self.debug = self._tex(F.rgba32_float, dw, dh)
        self.frame = 0
        self.net_values = (network.flat().reshape(-1, 4) if network else
                           np.zeros((121, 4), np.float32))

    def _kernel(self, name):
        src = flatten_source(name + ".hlsl")
        path = os.path.join(SHADER_DIR, name + ".hlsl")
        mod = self.dev.load_module_from_source(name, src, path)
        prog = self.dev.link_program([mod], [mod.entry_point("main")])
        return self.dev.create_compute_kernel(prog)

    def _tex(self, fmt, w, h, data=None):
        spy = self.spy
        usage = (spy.TextureUsage.shader_resource
                 | spy.TextureUsage.unordered_access)
        kw = {"data": np.ascontiguousarray(data)} if data is not None else {}
        return self.dev.create_texture(format=fmt, width=w, height=h,
                                       usage=usage, mip_count=1, **kw)

    def _constants(self, jitter, reset, sharpness, exposure):
        spy = self.spy
        rw, rh = self.render_size
        dw, dh = self.display_size
        flags = (core.FLAG_RESET if reset else 0) | (
            core.FLAG_NETWORK if self.network is not None else 0) | (
            core.FLAG_DEBUG)
        return {
            "g_RenderSize": spy.uint2(rw, rh),
            "g_DisplaySize": spy.uint2(dw, dh),
            "g_Jitter": spy.float2(*jitter),
            "g_MotionScale": spy.float2(1.0, 1.0),
            "g_DepthP0": 1.0, "g_DepthP1": 0.0,   # la scene fournit 1/z
            "g_Exposure": float(exposure),
            "g_Sharpness": float(sharpness),
            "g_Flags": int(flags),
            "g_SigmaSharp": float(np.float32(
                core.sigma_sharp(rw, dw, self.kernel_width))),
            "g_MaxCount": float(self.max_count),
            "g_ClipGamma": float(self.clip_gamma),
            "g_NetStrength": float(self.net_strength),
            "g_Reserved0": 0, "g_Reserved1": 0, "g_Reserved2": 0,
        }

    def _run(self, name, threads, consts, resources, net=False):
        spy = self.spy
        kernel = self.kernels[name]
        enc = self.dev.create_command_encoder()
        with enc.begin_compute_pass() as cp:
            cur = spy.ShaderCursor(cp.bind_pipeline(kernel.pipeline))
            cb = cur["USRConstants"]
            for k, v in consts.items():
                cb[k] = v
            if net:
                arr = cur["USRNetwork"]["g_Net"]
                for i, row in enumerate(self.net_values):
                    arr[i] = spy.float4(*[float(x) for x in row])
            for k, v in resources.items():
                cur[k] = v
            # slangpy compte en threads (il divise lui-meme par 8x8).
            cp.dispatch([threads[0], threads[1], 1])
        self.dev.submit_command_buffer(enc.finish())

    def dispatch(self, color, invz, motion, jitter, reset=False,
                 sharpness=0.0, exposure=1.0):
        F = self.spy.Format
        rw, rh = self.render_size
        dw, dh = self.display_size
        reset = reset or self.frame == 0
        cur, prev = self.frame % 2, (self.frame + 1) % 2
        rgba = np.concatenate([color, np.ones(color.shape[:2] + (1,))],
                              axis=-1).astype(np.float32)
        t_color = self._tex(F.rgba32_float, rw, rh, rgba)
        t_depth = self._tex(F.r32_float, rw, rh, invz.astype(np.float32))
        t_motion = self._tex(F.rg32_float, rw, rh,
                             motion.astype(np.float32))
        prev_invz = t_depth if self.frame == 0 else self.invz[prev]
        consts = self._constants(jitter, reset, sharpness, exposure)

        self._run("usr_prepare", (rw, rh), consts, {
            "t_Depth": t_depth, "t_Motion": t_motion,
            "t_PrevInvZ": prev_invz, "u_DilatedMotion": self.dilated_mv,
            "u_DilatedInvZ": self.invz[cur], "u_Disocclusion": self.disocc})
        self._run("usr_accumulate", (dw, dh), consts, {
            "t_Color": t_color, "t_DilatedMotion": self.dilated_mv,
            "t_Disocclusion": self.disocc, "t_History": self.history[prev],
            "u_HistoryOut": self.history[cur], "u_Debug": self.debug},
            net=True)
        self._run("usr_sharpen", (dw, dh), consts, {
            "t_HistoryNew": self.history[cur], "u_Output": self.output})
        self.dev.wait()
        self.frame += 1
        return self.output.to_numpy()[..., :3].astype(np.float32)

    def read_history(self):
        return self.history[(self.frame - 1) % 2].to_numpy().astype(
            np.float32)

    def read_debug(self):
        """(alpha, beta, confiance / max, desocclusion) par pixel."""
        return self.debug.to_numpy().astype(np.float32)

    def read_intermediates(self):
        return (self.dilated_mv.to_numpy().astype(np.float32),
                self.invz[(self.frame - 1) % 2].to_numpy().astype(np.float32),
                self.disocc.to_numpy().astype(np.float32))


# --------------------------------------------------------------------------
# USR Universel (sans vecteurs) : meme interface que
# universel.UniversalUpscaler, calcule par les shaders usr_u_*.hlsl.
# Sert aussi de modele au code hote C++ (meme enchainement de passes).
# --------------------------------------------------------------------------

U_FLAG_RESET = 1
U_FLAG_NETWORK = 2
U_FLAG_DEBUG = 4
U_FLAG_TOP = 8
U_FLAG_PERIOD = 16
U_FLAG_PREV = 32

U_KERNELS = ("usr_u_luma", "usr_u_down", "usr_u_grad", "usr_u_flow",
             "usr_u_median", "usr_u_finalize", "usr_u_residual",
             "usr_u_accumulate", "usr_u_output")


class GpuUniversal:
    def __init__(self, render_size, display_size, network=None, period=0,
                 net_strength=1.0, max_count=10.0, box_t1=0.3,
                 sharpness=0.0, device=None):
        from . import flow
        import slangpy as spy
        self.spy = spy
        self.dev = device or shared_device()
        self.render_size = tuple(render_size)
        self.display_size = tuple(display_size)
        self.network = network
        self.period = int(period) if 1 < int(period) <= flow.MAX_PERIOD \
            else 0
        self.net_strength = net_strength
        self.max_count = max_count
        self.box_t1 = box_t1
        self.sharpness = sharpness
        self.kernels = {n: self._kernel(n) for n in U_KERNELS}
        rw, rh = render_size
        dw, dh = display_size
        self.levels = flow.level_count(rw, rh)
        self.sizes = [(rw, rh)]
        for _ in range(self.levels - 1):
            w, h = self.sizes[-1]
            self.sizes.append(((w + 1) // 2, (h + 1) // 2))
        F = spy.Format
        tex = self._tex
        self.luma = [[tex(F.r32_float, w, h) for (w, h) in self.sizes]
                     for _ in range(2)]
        self.grad = [[tex(F.rg32_float, w, h) for (w, h) in self.sizes]
                     for _ in range(2)]
        self.ring_size = max(self.period, 1) + 1
        self.ring = [tex(F.r16_uint, rw, rh) for _ in range(self.ring_size)]
        self.motion_raw = [tex(F.rg32_float, w, h) for (w, h) in self.sizes]
        self.motion_med = [tex(F.rg32_float, w, h) for (w, h) in self.sizes]
        self.final = [tex(F.rg32_float, rw, rh) for _ in range(2)]
        self.aux = tex(F.rgba8_unorm, rw, rh)
        self.residual = tex(F.rgba16_float, rw, rh)
        self.history = [tex(F.rgba16_float, dw, dh) for _ in range(2)]
        self.output = tex(F.rgba32_float, dw, dh)
        self.debug = tex(F.rgba32_float, dw, dh)
        self.frame = 0          # images depuis la derniere remise a zero
        self.total = 0          # images depuis la creation (ping-pong)
        self.prev_jitter = (0.0, 0.0)
        self.net_values = (network.flat().reshape(-1, 4) if network else
                           np.zeros((121, 4), np.float32))

    def _kernel(self, name):
        src = flatten_source(name + ".hlsl")
        path = os.path.join(SHADER_DIR, name + ".hlsl")
        mod = self.dev.load_module_from_source(name, src, path)
        prog = self.dev.link_program([mod], [mod.entry_point("main")])
        return self.dev.create_compute_kernel(prog)

    def _tex(self, fmt, w, h, data=None):
        spy = self.spy
        usage = (spy.TextureUsage.shader_resource
                 | spy.TextureUsage.unordered_access)
        kw = {"data": np.ascontiguousarray(data)} if data is not None else {}
        return self.dev.create_texture(format=fmt, width=w, height=h,
                                       usage=usage, mip_count=1, **kw)

    def _constants(self, jitter, djitter, flags, level=0):
        spy = self.spy
        rw, rh = self.render_size
        dw, dh = self.display_size
        lw, lh = self.sizes[level]
        pw, ph = self.sizes[min(level + 1, self.levels - 1)]
        return {
            "g_RenderSize": spy.uint2(rw, rh),
            "g_DisplaySize": spy.uint2(dw, dh),
            "g_LevelSize": spy.uint2(lw, lh),
            "g_ParentSize": spy.uint2(pw, ph),
            "g_Jitter": spy.float2(float(np.float32(jitter[0])),
                                   float(np.float32(jitter[1]))),
            "g_JitterDelta": spy.float2(float(djitter[0]),
                                        float(djitter[1])),
            "g_Level": int(level),
            "g_Flags": int(flags),
            "g_NetStrength": float(self.net_strength),
            "g_MaxCount": float(self.max_count),
            "g_BoxT1": float(self.box_t1),
            "g_Sharpness": float(self.sharpness),
            "g_Reserved0": 0, "g_Reserved1": 0,
        }

    def _run(self, name, threads, consts, resources, net=False):
        spy = self.spy
        enc = self.dev.create_command_encoder()
        with enc.begin_compute_pass() as cp:
            cur = spy.ShaderCursor(cp.bind_pipeline(
                self.kernels[name].pipeline))
            cb = cur["USRUConstants"]
            for k, v in consts.items():
                cb[k] = v
            if net:
                arr = cur["USRNetwork"]["g_Net"]
                for i, row in enumerate(self.net_values):
                    arr[i] = spy.float4(*[float(x) for x in row])
            for k, v in resources.items():
                cur[k] = v
            cp.dispatch([threads[0], threads[1], 1])
        self.dev.submit_command_buffer(enc.finish())

    def reset(self):
        self.frame = 0

    def dispatch(self, image, jitter=(0.0, 0.0), reset=False):
        F = self.spy.Format
        rw, rh = self.render_size
        dw, dh = self.display_size
        if reset:
            self.frame = 0
        n = self.frame
        cur, prev = self.total % 2, (self.total + 1) % 2
        K = self.ring_size
        has_prev = n >= 1
        djit = (np.float32(jitter[0] - self.prev_jitter[0]),
                np.float32(jitter[1] - self.prev_jitter[1])) if has_prev \
            else (np.float32(0.0), np.float32(0.0))
        rgba = np.concatenate([np.asarray(image, np.float32),
                               np.ones(image.shape[:2] + (1,), np.float32)],
                              axis=-1)
        color = self._tex(F.rgba32_float, rw, rh, rgba)
        base = 0

        def c(flags, level=0):
            return self._constants(jitter, djit, flags, level)

        ring_cur = self.ring[n % K]
        ring_prev = self.ring[(n - 1) % K]
        ring_phase = self.ring[(n - self.period) % K] if self.period else \
            ring_prev
        self._run("usr_u_luma", (rw, rh), c(base), {
            "t_Color": color, "u_Luma": self.luma[cur][0],
            "u_Luma16": ring_cur})
        for k in range(self.levels - 1):
            w, h = self.sizes[k + 1]
            self._run("usr_u_down", (w, h), c(base, k), {
                "t_Level": self.luma[cur][k], "u_Down": self.luma[cur][k + 1]})
        for k in range(self.levels):
            w, h = self.sizes[k]
            self._run("usr_u_grad", (w, h), c(base, k), {
                "t_Level": self.luma[cur][k], "u_Grad": self.grad[cur][k]})
        if has_prev:
            for lvl in range(self.levels - 1, -1, -1):
                w, h = self.sizes[lvl]
                top = lvl == self.levels - 1
                parent = self.motion_med[lvl + 1] if not top else \
                    self.motion_med[lvl]
                self._run("usr_u_flow", (w, h),
                          c(U_FLAG_TOP if top else 0, lvl), {
                              "t_Cur": self.luma[cur][lvl],
                              "t_Prev": self.luma[prev][lvl],
                              "t_PrevGrad": self.grad[prev][lvl],
                              "t_Parent": parent,
                              "t_Temporal": self.final[prev],
                              "u_Motion": self.motion_raw[lvl]})
                self._run("usr_u_median", (w, h), c(0, lvl), {
                    "t_Motion": self.motion_raw[lvl],
                    "u_Median": self.motion_med[lvl]})
        fl = (U_FLAG_PREV if has_prev else 0) | (
            U_FLAG_PERIOD if self.period and n >= self.period else 0)
        self._run("usr_u_finalize", (rw, rh), c(fl), {
            "t_Cur": self.luma[cur][0], "t_Prev": self.luma[prev][0],
            "t_Motion": self.motion_med[0], "t_Cur16": ring_cur,
            "t_Prev16": ring_prev, "t_Phase16": ring_phase,
            "u_Final": self.final[cur], "u_Aux": self.aux})
        first = n == 0
        fa = (U_FLAG_RESET if first else 0) | U_FLAG_DEBUG | (
            U_FLAG_NETWORK if self.network is not None else 0)
        self._run("usr_u_residual", (rw, rh), c(fa), {
            "t_Color": color, "t_Motion": self.final[cur], "t_Aux": self.aux,
            "t_History": self.history[prev], "u_Residual": self.residual})
        self._run("usr_u_accumulate", (dw, dh), c(fa), {
            "t_Color": color, "t_Motion": self.final[cur], "t_Aux": self.aux,
            "t_History": self.history[prev], "t_Residual": self.residual,
            "u_HistoryOut": self.history[cur], "u_Debug": self.debug},
            net=True)
        self._run("usr_u_output", (dw, dh), c(fa), {
            "t_History": self.history[cur], "u_Output": self.output})
        self.dev.wait()
        self.prev_jitter = (float(jitter[0]), float(jitter[1]))
        self.frame += 1
        self.total += 1
        return self.output.to_numpy()[..., :3].astype(np.float32)

    def read(self, what):
        """Intermediaires pour les tests : 'motion', 'aux', 'residual',
        'history', 'debug'."""
        cur = (self.total - 1) % 2
        tex = {"motion": self.final[cur], "aux": self.aux,
               "residual": self.residual, "history": self.history[cur],
               "debug": self.debug}[what]
        return tex.to_numpy().astype(np.float32)
