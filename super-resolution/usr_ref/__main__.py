"""Ligne de commande de la reference USR.

    python -m usr_ref demo          # compare les methodes, ecrit des PNG
    python -m usr_ref banc          # tableau PSNR / scintillement
    python -m usr_ref entrainer     # re-entraine le reseau (quelques minutes)
    python -m usr_ref exporter      # regenere src/usr_default_weights.h
    python -m usr_ref parite        # shaders GPU vs reference (slangpy)
    python -m usr_ref labo-actifs   # ressources de l'appli USR Labo
"""

import argparse
import os
import sys

import numpy as np

from . import __version__, core, evaluate
from .network import Network, default_weights_path, load_default
from .scene import Scene

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEADER = os.path.join(ROOT, "src", "usr_default_weights.h")


def _load(path):
    net = Network.load(path) if path else load_default()
    if net is None:
        print("(aucun poids trouve : reseau desactive)")
    return net


def cmd_demo(args):
    net = _load(args.poids)
    size = (args.largeur, args.hauteur)
    scene = Scene(seed=args.scene, static=args.fixe, cache_gt=True)
    os.makedirs(args.sortie, exist_ok=True)
    last = args.images - 1
    print("Scene %d, %dx%d, mode %s (rendu %dx%d), %d images" % (
        args.scene, size[0], size[1], args.mode,
        *core.render_size(size, args.mode), args.images))
    tiles = []
    for method in ("bilineaire", "heuristique", "ia"):
        if method == "ia" and net is None:
            continue
        r = evaluate.run(scene, size, args.mode, args.images, method, net,
                         sharpness=args.nettete, keep=(last,))
        out, gt = r["images"][last]
        print("  %-12s PSNR %6.2f dB   scintillement %.4f" % (
            method, r["psnr"], r["scintillement"]))
        img = evaluate.to_srgb8(out)
        evaluate.write_png(os.path.join(args.sortie, method + ".png"), img)
        tiles.append(img)
    gt8 = evaluate.to_srgb8(gt)
    evaluate.write_png(os.path.join(args.sortie, "verite.png"), gt8)
    tiles.append(gt8)
    # planche : un recadrage agrandi de chaque methode, cote a cote
    h, w = gt8.shape[:2]
    y0, x0 = h // 4, w // 4
    crops = [evaluate.zoom(t[y0:y0 + h // 2, x0:x0 + w // 2], 3)
             for t in tiles]
    sep = np.full((crops[0].shape[0], 6, 3), 255, np.uint8)
    board = np.concatenate(sum([[c, sep] for c in crops], [])[:-1], axis=1)
    evaluate.write_png(os.path.join(args.sortie, "comparaison.png"), board)
    print("Images dans %s/ (comparaison.png : %s, verite)" % (
        args.sortie, ", ".join(("bilineaire", "heuristique", "ia")[
            :len(tiles) - 1])))


def cmd_banc(args):
    net = _load(args.poids)
    evaluate.benchmark(net, frames=args.images, modes=args.modes)


def cmd_entrainer(args):
    from . import train
    kw = dict(n_seeds=2, frames=16, rounds=2, steps=800) if args.rapide \
        else {}
    net, meta = train.train(stability=args.stabilite, **kw)
    out = args.sortie or default_weights_path()
    net.save(out, os.path.splitext(out)[0] + ".bin", meta)
    net.to_c_header(HEADER, "Source : %s" % os.path.basename(out))
    print("Poids ecrits : %s (+ .bin, + %s)" % (out, os.path.relpath(
        HEADER, ROOT)))
    evaluate.benchmark(net, frames=40)


def cmd_exporter(args):
    path = args.poids or default_weights_path()
    net = Network.load(path)
    net.flat().tofile(os.path.splitext(path)[0] + ".bin")
    net.to_c_header(HEADER, "Source : %s" % os.path.basename(path))
    print("Ecrit : %s et %s" % (os.path.splitext(path)[0] + ".bin", HEADER))


def cmd_parite(args):
    from . import gpu
    if not gpu.available():
        print("slangpy absent : pip install slangpy (et un pilote Vulkan)")
        return 1
    net = _load(args.poids)
    size = (args.largeur, args.hauteur)
    rsize = core.render_size(size, args.mode)
    phases = core.jitter_phase_count(rsize[0], size[0])
    scene = Scene(seed=args.scene)
    g = gpu.GpuUpscaler(rsize, size, network=net)
    r = core.Upscaler(rsize, size, network=net)
    print("GPU : %s" % g.dev.info.adapter_name)
    worst = 1e9
    for f in range(args.images):
        j = core.jitter_offset(f, phases)
        color, invz, motion = scene.render(f, rsize, j)
        og = g.dispatch(color, invz, motion, j, sharpness=0.5)
        orf = r.dispatch(color, invz, motion, j, sharpness=0.5)
        p = evaluate.psnr(og, orf)
        worst = min(worst, p)
        print("  image %2d : GPU vs reference %.1f dB" % (f, p))
    ok = worst > 55.0
    print("PARITE %s (pire image %.1f dB, seuil 55 dB)" % (
        "OK" if ok else "ECHEC", worst))
    return 0 if ok else 1


def cmd_labo_actifs(args):
    from . import labo
    labo.generate_all()


def cmd_universel_entree(args):
    from . import universel
    images, jitters, period = universel.banc_sequence(args.images)
    universel.write_banc_input(args.fichier, images, jitters, (192, 108),
                               (384, 216), period,
                               no_network=args.sans_reseau)
    print("Ecrit : %s (%d images, periode de jitter %d)" % (
        args.fichier, len(images), period))


def main(argv=None):
    p = argparse.ArgumentParser(prog="python -m usr_ref",
                                description="Reference USR v" + __version__)
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("demo", help="compare les methodes et ecrit des PNG")
    d.add_argument("--mode", default="performance",
                   choices=sorted(core.QUALITY_MODES))
    d.add_argument("--scene", type=int, default=101)
    d.add_argument("--fixe", action="store_true", help="camera immobile")
    d.add_argument("--images", type=int, default=40)
    d.add_argument("--largeur", type=int, default=384)
    d.add_argument("--hauteur", type=int, default=216)
    d.add_argument("--nettete", type=float, default=0.0)
    d.add_argument("--poids")
    d.add_argument("--sortie", default="resultats")
    d.set_defaults(func=cmd_demo)

    b = sub.add_parser("banc", help="PSNR et scintillement, scenes inedites")
    b.add_argument("--poids")
    b.add_argument("--images", type=int, default=40)
    b.add_argument("--modes", nargs="+", default=["performance"],
                   choices=sorted(core.QUALITY_MODES))
    b.set_defaults(func=cmd_banc)

    e = sub.add_parser("entrainer", help="re-entraine le reseau")
    e.add_argument("--rapide", action="store_true",
                   help="petit entrainement pour essayer (~1 min)")
    e.add_argument("--stabilite", type=float, default=1.0)
    e.add_argument("--sortie")
    e.set_defaults(func=cmd_entrainer)

    x = sub.add_parser("exporter", help="poids JSON -> .bin + en-tete C++")
    x.add_argument("poids", nargs="?")
    x.set_defaults(func=cmd_exporter)

    g = sub.add_parser("parite", help="shaders GPU vs reference NumPy")
    g.add_argument("--mode", default="performance",
                   choices=sorted(core.QUALITY_MODES))
    g.add_argument("--scene", type=int, default=3)
    g.add_argument("--images", type=int, default=8)
    g.add_argument("--largeur", type=int, default=128)
    g.add_argument("--hauteur", type=int, default=72)
    g.add_argument("--poids")
    g.set_defaults(func=cmd_parite)

    la = sub.add_parser("labo-actifs",
                        help="regenere police, scene, modeles et icones "
                             "du Labo (necessite Pillow)")
    la.set_defaults(func=cmd_labo_actifs)

    ue = sub.add_parser("universel-entree",
                        help="sequence d'entree du banc de bout en bout "
                             "(tests/wine/universel_wine.sh)")
    ue.add_argument("fichier")
    ue.add_argument("--images", type=int, default=16)
    ue.add_argument("--sans-reseau", action="store_true")
    ue.set_defaults(func=cmd_universel_entree)

    args = p.parse_args(argv)
    return args.func(args) or 0


if __name__ == "__main__":
    sys.exit(main())
