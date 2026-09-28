"""Ressources de USR Labo, generees depuis la reference Python.

    python -m usr_ref labo-actifs     # regenere tout (necessite Pillow)

* ``labo/src/labo_font.h``         police bitmap (DejaVu Sans Mono Bold,
                                   accents francais, symboles du menu) ;
* ``labo/src/labo_scene_params.h`` la scene de test (Scene(seed=101)) ;
* ``labo/src/labo_models.h``       les trois modeles du reseau ;
* ``labo/uwp/Assets/*.png``        icones de l'application UWP.

Et, sans Pillow, ``scene_constants`` : le contenu exact du cbuffer
LaboScene pour un instant donne (utilise par les tests de parite).
"""

import os

import numpy as np

from .network import Network
from .scene import Scene

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LABO = os.path.join(ROOT, "labo")
SRC = os.path.join(LABO, "src")

LABO_SEED = 101
MAX_OBJECTS = 8

GLYPH_W, GLYPH_H = 12, 24
WORDS_PER_ROW = (GLYPH_W + 3) // 4
FONT_FILE = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"
EXTRA_CHARS = ("àâäçéèêëîïôöùûüÿœæÀÂÄÇÉÈÊËÎÏÔÖÙÛÜŸŒÆ«»°±×÷·…–—‘’“”€²³µ"
               "◀▶►●○▲▼←→↑↓✓█")

MODELS = (("stable", "usr_net_stable.json"),
          ("equilibre", "usr_net.json"),
          ("detail", "usr_net_detail.json"))


# --------------------------------------------------------------------------
# Scene : ce que le CPU envoie au GPU a chaque image
# --------------------------------------------------------------------------

def labo_scene():
    return Scene(seed=LABO_SEED)


def scene_constants(scene, t, t_prev=None):
    """Contenu du cbuffer LaboScene (labo_scene.hlsli) a l'instant t.

    Par defaut l'image precedente est a t - 1, comme dans Scene.shade.
    """
    t_prev = t - 1.0 if t_prev is None else t_prev
    cam, cam_prev = scene.camera(t), scene.camera(t_prev)
    objects = []
    for obj in sorted(scene.objects, key=lambda o: -o["depth"]):
        c = scene.object_center(obj, t)
        cp = scene.object_center(obj, t_prev)
        objects.append({
            "centers": [float(c[0]), float(c[1]), float(cp[0]), float(cp[1])],
            "shape": [float(obj["radius"]), float(obj["depth"]),
                      float(obj["rings"]),
                      0.0 if obj["shape"] == "disc" else 1.0],
            "tint": [float(x) for x in obj["tint"]] + [0.0],
        })
    return {
        "g_Camera": [float(cam[0]), float(cam[1]), float(cam_prev[0]),
                     float(cam_prev[1])],
        "g_Aspect": float(scene.aspect),
        "g_ScreenPhase": float((0.09 * t) % 1.0),
        "g_NeonOn": int((int(np.floor(t / 7.0)) % 2) == 0),
        "g_ObjectCount": len(objects),
        "objects": objects,
    }


# --------------------------------------------------------------------------
# En-tetes C++
# --------------------------------------------------------------------------

def _floats(values):
    return ", ".join("%.17g" % v for v in values)


def write_scene_header(path=None, scene=None):
    scene = scene or labo_scene()
    path = path or os.path.join(SRC, "labo_scene_params.h")
    lines = [
        "// Genere par `python -m usr_ref labo-actifs` -- ne pas editer.",
        "// La scene de test de usr_ref (Scene(seed=%d)), pour que le Labo"
        % LABO_SEED,
        "// affiche exactement ce qui a servi a entrainer et mesurer USR.",
        "#pragma once",
        "",
        "namespace labo { namespace scene {",
        "",
        "struct ObjectParams {",
        "    double base[2], amp[2], freq[2], phase[2];",
        "    double radius, depth, rings;",
        "    double tint[3];",
        "    bool box;",
        "};",
        "",
        "static const double kAspect = %.17g;" % scene.aspect,
        "static const double kCam0[2] = {%s};" % _floats(scene.cam0),
        "static const double kCameraSpeed[2] = {%s};" % _floats(
            scene.camera_speed),
        "static const double kWobble = %.17g;" % scene.wobble,
        "static const unsigned kObjectCount = %d;" % len(scene.objects),
        "static const ObjectParams kObjects[%d] = {" % len(scene.objects),
    ]
    for o in scene.objects:
        lines.append("    {{%s}, {%s}, {%s}, {%s}, %.17g, %.17g, %.17g, "
                     "{%s}, %s}," % (
                         _floats(o["base"]), _floats(o["amp"]),
                         _floats(o["freq"]), _floats(o["phase"]),
                         o["radius"], o["depth"], o["rings"],
                         _floats(o["tint"]),
                         "false" if o["shape"] == "disc" else "true"))
    lines += ["};", "", "}} // namespace labo::scene", ""]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return path


def write_models_header(path=None):
    path = path or os.path.join(SRC, "labo_models.h")
    lines = [
        "// Genere par `python -m usr_ref labo-actifs` -- ne pas editer.",
        "// Les trois modeles du reseau USR proposes dans le Labo.",
        "#pragma once",
        "",
        "namespace labo { namespace models {",
        "",
        "static const unsigned kWeightCount = 484;",
    ]
    names = []
    for name, filename in MODELS:
        net = Network.load(os.path.join(ROOT, "weights", filename))
        v = net.flat()
        lines.append("alignas(16) static const float k_%s[484] = {" % name)
        for i in range(0, len(v), 4):
            lines.append("    " + ", ".join("%.9ef" % x for x in v[i:i + 4])
                         + ",")
        lines.append("};")
        names.append(name)
    lines += ["", "static const float* const kModels[%d] = {%s};" % (
        len(names), ", ".join("k_" + n for n in names)),
        "", "}} // namespace labo::models", ""]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return path


def font_codepoints():
    chars = [chr(c) for c in range(32, 127)] + list(EXTRA_CHARS)
    seen, out = set(), []
    for ch in chars:
        if ord(ch) not in seen:
            seen.add(ord(ch))
            out.append(ord(ch))
    return sorted(out)


def render_font():
    """Rend chaque glyphe en couverture 8 bits, GLYPH_W x GLYPH_H."""
    from PIL import Image, ImageDraw, ImageFont
    font = ImageFont.truetype(FONT_FILE, 20)
    cps = font_codepoints()
    data = np.zeros((len(cps), GLYPH_H, WORDS_PER_ROW * 4), np.uint8)
    for gi, cp in enumerate(cps):
        if cp == 32:
            continue
        img = Image.new("L", (GLYPH_W, GLYPH_H), 0)
        ImageDraw.Draw(img).text((0, 19), chr(cp), fill=255, font=font,
                                 anchor="ls")
        data[gi, :, :GLYPH_W] = np.asarray(img)
    return cps, data


def write_font_header(path=None):
    path = path or os.path.join(SRC, "labo_font.h")
    cps, data = render_font()
    words = data.reshape(len(cps), GLYPH_H, WORDS_PER_ROW, 4).astype(
        np.uint32)
    words = (words[..., 0] | (words[..., 1] << 8) | (words[..., 2] << 16)
             | (words[..., 3] << 24)).ravel()
    lines = [
        "// Genere par `python -m usr_ref labo-actifs` -- ne pas editer.",
        "// Police bitmap du Labo : DejaVu Sans Mono Bold (licence Bitstream",
        "// Vera / domaine public), couverture 8 bits, 4 pixels par mot.",
        "#pragma once",
        "",
        "#include <cstdint>",
        "",
        "namespace labo { namespace font {",
        "",
        "static const uint32_t kGlyphWidth = %d;" % GLYPH_W,
        "static const uint32_t kGlyphHeight = %d;" % GLYPH_H,
        "static const uint32_t kWordsPerRow = %d;" % WORDS_PER_ROW,
        "static const uint32_t kGlyphCount = %d;" % len(cps),
        "// Points de code tries ; l'indice est le numero du glyphe (0 = espace).",
        "static const uint32_t kCodepoints[%d] = {" % len(cps),
    ]
    for i in range(0, len(cps), 12):
        lines.append("    " + ", ".join("0x%04X" % c for c in cps[i:i + 12])
                     + ",")
    lines += ["};", "static const uint32_t kData[%d] = {" % len(words)]
    for i in range(0, len(words), 8):
        lines.append("    " + ", ".join("0x%08Xu" % int(w)
                                        for w in words[i:i + 8]) + ",")
    lines += ["};", "", "}} // namespace labo::font", ""]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return path


def read_font_header(path=None):
    """Relit la police generee (sans Pillow) : (points de code, mots)."""
    import re
    path = path or os.path.join(SRC, "labo_font.h")
    with open(path, encoding="utf-8") as f:
        text = f.read()
    cps_block = re.search(r"kCodepoints\[\d+\] = \{(.*?)\};", text, re.S)
    data_block = re.search(r"kData\[\d+\] = \{(.*?)\};", text, re.S)
    cps = [int(x, 16) for x in re.findall(r"0x([0-9A-F]+)",
                                          cps_block.group(1))]
    words = [int(x, 16) for x in re.findall(r"0x([0-9A-F]+)u",
                                            data_block.group(1))]
    return cps, np.array(words, np.uint32)


# --------------------------------------------------------------------------
# Icones UWP
# --------------------------------------------------------------------------

ICONS = {
    "Square44x44Logo.png": (44, 44),
    "Square150x150Logo.png": (150, 150),
    "Wide310x150Logo.png": (310, 150),
    "StoreLogo.png": (50, 50),
    "SplashScreen.png": (620, 300),
}


def write_icons(directory=None):
    from PIL import Image, ImageDraw, ImageFont
    directory = directory or os.path.join(LABO, "uwp", "Assets")
    os.makedirs(directory, exist_ok=True)
    for name, (w, h) in ICONS.items():
        img = Image.new("RGB", (w, h))
        px = img.load()
        for y in range(h):
            for x in range(w):
                t = (x / max(w - 1, 1) + y / max(h - 1, 1)) / 2
                px[x, y] = (int(20 + 40 * t), int(24 + 30 * t),
                            int(60 + 120 * t))
        draw = ImageDraw.Draw(img)
        size = max(10, int(min(w, h) * 0.42))
        font = ImageFont.truetype(FONT_FILE, size)
        draw.text((w / 2, h / 2), "USR", fill=(255, 214, 64), font=font,
                  anchor="mm")
        if h >= 150:
            small = ImageFont.truetype(FONT_FILE, max(10, size // 3))
            draw.text((w / 2, h / 2 + size * 0.75), "Labo",
                      fill=(200, 220, 255), font=small, anchor="mm")
        img.save(os.path.join(directory, name))
    return directory


def generate_all(log=print):
    log("Police      : %s" % write_font_header())
    log("Scene       : %s" % write_scene_header())
    log("Modeles     : %s" % write_models_header())
    log("Icones UWP  : %s" % write_icons())


# --------------------------------------------------------------------------
# Composition de l'ecran (jumeau de labo/shaders/labo_compose.hlsl)
# --------------------------------------------------------------------------

VIEW_COLOR, VIEW_ALPHA, VIEW_BETA, VIEW_CONFIDENCE, VIEW_DISOCCLUSION, \
    VIEW_MOTION = range(6)
CELL_PANEL = 0x00010000
CELL_HIGHLIGHT = 0x00020000

PALETTE = np.array([
    [0.95, 0.95, 0.95], [0.60, 0.62, 0.68], [1.00, 0.84, 0.25],
    [0.45, 0.85, 1.00], [0.45, 0.95, 0.50], [1.00, 0.45, 0.40],
    [1.00, 0.62, 0.25], [0.80, 0.55, 1.00]], np.float32)


def labo_display(c):
    c = np.maximum(c, 0.0)
    y = c / (1.0 + np.max(c, axis=-1, keepdims=True))
    return np.power(np.clip(y, 0.0, 1.0), 1.0 / 2.2)


def ramp(s):
    s = np.clip(s, 0.0, 1.0)[..., None]
    stops = np.array([[0.05, 0.05, 0.35], [0.00, 0.60, 0.90],
                      [0.20, 0.85, 0.30], [0.98, 0.85, 0.15],
                      [0.90, 0.15, 0.10]], np.float32)
    t = s * 4.0
    seg = np.clip(np.floor(t), 0, 3).astype(int)[..., 0]
    f = t - seg[..., None]
    return stops[seg] + (stops[seg + 1] - stops[seg]) * f


def hsv(h, s, v):
    k = np.clip(np.abs(np.mod(h[..., None] + np.array([0.0, 2 / 3, 1 / 3]),
                              1.0) * 6.0 - 3.0) - 1.0, 0.0, 1.0)
    return v[..., None] * (1.0 + (k - 1.0) * s[..., None])


def compose_reference(c, left, right, debug, motion, font_words, text):
    """Image composee (float, avant quantification 8 bits).

    ``c`` : dict des constantes de LaboComposePass (memes noms, sans g_).
    """
    w, h = c["OutSize"]
    ys, xs = np.mgrid[0:h, 0:w]
    zc = np.array(c["ZoomCenter"], np.float32)
    fx = xs + 0.5 - zc[0]
    fy = ys + 0.5 - zc[1]
    dist = np.sqrt(fx * fx + fy * fy)
    in_lens = (c["ZoomFactor"] > 0) & (dist < c["ZoomRadius"])
    zf = c["ZoomFactor"] if c["ZoomFactor"] > 0 else 1.0
    sx = np.where(in_lens, np.floor(zc[0] + fx / zf), xs).astype(int)
    sy = np.where(in_lens, np.floor(zc[1] + fy / zf), ys).astype(int)
    left_side = np.maximum(sx, 0) < c["SplitX"]
    view = np.where(left_side, c["LeftView"], c["RightView"])
    px = np.clip(sx, 0, w - 1)
    py = np.clip(sy, 0, h - 1)

    color = np.where(left_side[..., None], labo_display(left[py, px]),
                     labo_display(right[py, px]))
    d = debug[py, px]
    for v, ch in ((VIEW_ALPHA, 0), (VIEW_BETA, 1), (VIEW_CONFIDENCE, 2),
                  (VIEW_DISOCCLUSION, 3)):
        s = np.sqrt(d[..., ch]) if v == VIEW_ALPHA else d[..., ch]
        color = np.where((view == v)[..., None], ramp(s), color)
    mw, mh = c["MotionSize"]
    mx = np.clip((px * np.float32(mw) / np.float32(w)).astype(int), 0, mw - 1)
    my = np.clip((py * np.float32(mh) / np.float32(h)).astype(int), 0, mh - 1)
    mv = motion[my, mx]
    length = np.sqrt(mv[..., 0] ** 2 + mv[..., 1] ** 2)
    angle = np.arctan2(mv[..., 1], mv[..., 0]) / (2 * np.pi) + 0.5
    sat = np.clip(length / c["MotionScale"], 0.0, 1.0)
    color = np.where((view == VIEW_MOTION)[..., None],
                     hsv(angle, sat, 0.25 + 0.75 * sat), color)

    ring = in_lens & (dist > c["ZoomRadius"] - 3.0)
    color = np.where(ring[..., None], np.array([1.0, 0.84, 0.25]), color)
    split = (~in_lens) & (c["SplitX"] < w) & (np.abs(xs - c["SplitX"]) <= 1)
    color = np.where(split[..., None], 1.0, color)

    cols, rows = c["TextGrid"]
    cw, ch = c["CellSize"]
    gw, gh = c["GlyphSize"]
    cx, cy = xs // cw, ys // ch
    inside = (cx < cols) & (cy < rows)
    v = np.where(inside, text[np.clip(cy, 0, rows - 1) * cols
                              + np.clip(cx, 0, cols - 1)], 0).astype(np.uint32)
    color = np.where(((v & CELL_PANEL) != 0)[..., None], color * 0.25, color)
    hi = np.array([0.25, 0.32, 0.55])
    color = np.where(((v & CELL_HIGHLIGHT) != 0)[..., None],
                     color + (hi - color) * 0.85, color)
    glyph = v & 0xFFF
    lx = ((xs - cx * cw) * gw) // cw
    ly = ((ys - cy * ch) * gh) // ch
    rw = (gw + 3) // 4
    idx = (glyph * gh + ly) * rw + lx // 4
    cover = ((font_words[idx] >> ((lx & 3) * 8).astype(np.uint32)) & 0xFF
             ) / 255.0
    ink = PALETTE[(v >> 12) & 7]
    cover = np.where(glyph != 0, cover, 0.0)[..., None]
    return color + (ink - color) * cover


# --------------------------------------------------------------------------
# Captures du mode --capture de l'application (verification de bout en bout)
# --------------------------------------------------------------------------

def read_capture(path):
    """Lit un frame_NNN.bin ecrit par ``usr_labo --capture``."""
    with open(path, "rb") as f:
        data = f.read()
    if data[:7] != b"USRCAP1":
        raise ValueError("pas une capture USR Labo : %s" % path)
    dw, dh, rw, rh = np.frombuffer(data, "<u4", 4, 8)
    jitter = np.frombuffer(data, "<f4", 2, 24)
    off = 32

    def take(dtype, count, shape):
        nonlocal off
        arr = np.frombuffer(data, dtype, count, off).reshape(shape)
        off += arr.nbytes
        return arr

    dw, dh, rw, rh = int(dw), int(dh), int(rw), int(rh)
    cap = {
        "display": (dw, dh), "render": (rw, rh),
        "jitter": (float(jitter[0]), float(jitter[1])),
        "composed": take("<u1", dw * dh * 4, (dh, dw, 4)),
        "usr": take("<f2", dw * dh * 4, (dh, dw, 4)).astype(np.float32),
        "color": take("<f2", rw * rh * 4, (rh, rw, 4)).astype(np.float32),
        "depth": take("<f4", rw * rh, (rh, rw)).astype(np.float32),
        "motion_px": take("<f2", rw * rh * 2, (rh, rw, 2)).astype(np.float32),
    }
    if off != len(data):
        raise ValueError("taille de capture inattendue : %s" % path)
    return cap


def replay_captures(paths, network, **settings):
    """Rejoue les entrees capturees dans la reference NumPy et renvoie, pour
    chaque image, (sortie de l'application, sortie de la reference)."""
    from . import core
    first = read_capture(paths[0])
    rw, rh = first["render"]
    up = core.Upscaler(first["render"], first["display"], network=network,
                       **settings)
    scale = np.array([np.float32(1.0) / np.float32(rw),
                      np.float32(1.0) / np.float32(rh)], np.float32)
    out = []
    for p in paths:
        cap = read_capture(p)
        ref = up.dispatch(cap["color"][..., :3], cap["depth"],
                          cap["motion_px"] * scale, cap["jitter"])
        out.append((cap["usr"][..., :3], ref))
    return out
