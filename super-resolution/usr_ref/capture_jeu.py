"""Captures de vrais jeux (Xenia, variable usr_capture) : lecture, et
sequences d'entrainement et de mesure. Protocole : docs/CAPTURE.md.

Xenia rend le jeu a l'echelle 3 (draw_resolution_scale), sans jitter, et
enregistre des sequences de 48 images consecutives d'une decoupe de
384x216 pixels, telle que USR la recevrait (apres la rampe gamma, 10 bits
par canal).

Pourquoi l'echelle 3 : l'image a l'echelle 3 contient exactement les
9 images a l'echelle 1 que donnerait le jitter en grille 3x3 du niveau 2.
Le pixel k a l'echelle 1, decale de ((i + 0,5) / 3 - 0,5) pixel, echantillonne
la scene au centre du pixel 3k + i a l'echelle 3. Decimer une image sur 3,
a la phase (i, j), donne donc l'image que le jeu aurait rendue a
l'echelle 1 avec ce jitter. Et l'image a l'echelle 3 elle-meme est la
verite terrain, a la taille d'affichage du rapport 3.

Ce que la decimation ne reproduit pas :
* le choix des mip-maps : le jeu a l'echelle 3 prend des textures 3 fois
  plus fines (comme un biais de -1,6), la ou le niveau 2 en prend 2 fois
  (biais -1) ;
* le HUD : decime avec la scene, il « bouge » avec le jitter, alors que
  Xenia ne decale que les dessins avec profondeur ;
* la verite n'est pas sur-echantillonnee : c'est une image rendue a
  l'echelle 3, avec son propre crenelage.
"""

import os

import numpy as np

from . import universel

MAGIC = 0x43525355        # 'USRC'
HEADER_WORDS = 10
DXGI_R10G10B10A2_UNORM = 24
SCALE = 3


def lire(path):
    """Renvoie (en-tete, images) ; images : liste de (h, w, 3) float32 dans
    [0, 1]. Une sequence interrompue garde ses images completes."""
    raw = np.fromfile(path, "<u4")
    if raw.size < HEADER_WORDS or raw[0] != MAGIC:
        raise ValueError("%s : pas une capture USR" % path)
    (_, version, w, h, sx, sy, fmt, planned, cx, cy) = [
        int(x) for x in raw[:HEADER_WORDS]]
    if version != 1 or fmt != DXGI_R10G10B10A2_UNORM:
        raise ValueError("%s : version %d, format %d non pris en charge" % (
            path, version, fmt))
    header = {"largeur": w, "hauteur": h, "echelle": (sx, sy),
              "images_prevues": planned, "decoupe": (cx, cy)}
    body = raw[HEADER_WORDS:]
    n = body.size // (w * h)
    words = body[:n * w * h].reshape(n, h, w)
    rgb = np.stack([(words >> s) & 0x3FF for s in (0, 10, 20)], axis=-1)
    frames = [(f.astype(np.float32) / np.float32(1023.0)) for f in rgb]
    header["images"] = n
    return header, frames


def ecrire(path, frames, crop=(0, 0)):
    """Ecrit une capture au format de Xenia (pour les tests)."""
    h, w = frames[0].shape[:2]
    head = np.array([MAGIC, 1, w, h, SCALE, SCALE, DXGI_R10G10B10A2_UNORM,
                     len(frames), crop[0], crop[1]], "<u4")
    with open(path, "wb") as f:
        f.write(head.tobytes())
        for img in frames:
            q = np.round(np.clip(img, 0.0, 1.0) * 1023.0).astype(np.uint32)
            word = q[..., 0] | (q[..., 1] << 10) | (q[..., 2] << 20) | (
                np.uint32(3) << 30)
            f.write(word.astype("<u4").tobytes())


def decimer(frame, phase):
    """Image a l'echelle 1 vue avec le jitter de la phase (i, j)."""
    i, j = phase
    return np.ascontiguousarray(frame[j::SCALE, i::SCALE])


def sequence(frames, niveau):
    """Sequence au format de train_universel (rapport 3) : images a
    l'echelle 1, jitter, verite. Niveau 2 : jitter en grille 3x3, dans
    l'ordre de universel.GRID_ORDER ; niveau 1 : toujours la phase du
    centre, jitter nul."""
    h, w = frames[0].shape[:2]
    if h % SCALE or w % SCALE:
        raise ValueError("decoupe %dx%d non divisible par %d" % (w, h, SCALE))
    order = universel.GRID_ORDER[SCALE]
    items, gts = [], []
    for f, frame in enumerate(frames):
        if niveau == 2:
            i, j = order[f % len(order)]
        else:
            i, j = 1, 1
        jit = (np.float32((i + 0.5) / SCALE - 0.5),
               np.float32((j + 0.5) / SCALE - 0.5))
        img = decimer(frame, (i, j))
        items.append((img, jit, np.zeros(img.shape[:2] + (2,), np.float32)))
        gts.append(frame)
    return {"spec": ("capture", None, SCALE, niveau, 0.0),
            "rsize": (w // SCALE, h // SCALE),
            "period": SCALE * SCALE if niveau == 2 else 0,
            "items": items, "gt": gts}


# Une capture sur RESERVE n'est jamais vue a l'entrainement : c'est sur
# elles que se mesure un reseau entraine avec les autres. Mesurer sur les
# captures apprises donnerait un gain flatteur et faux.
RESERVE = 4


def fichiers(dossier, part=None):
    """Captures du dossier ; ``part`` : None (toutes), « entrainement » ou
    « mesure » (la reserve). Moins de RESERVE captures : pas de reserve,
    les deux parts sont toutes les captures."""
    tous = sorted(os.path.join(dossier, n) for n in os.listdir(dossier)
                  if n.startswith("usrc_") and n.endswith(".bin"))
    if part is None or len(tous) < RESERVE:
        return tous
    reserve = tous[RESERVE - 1::RESERVE]
    if part == "mesure":
        return reserve
    return [p for p in tous if p not in reserve]


def mesurer(dossier, network, log=print, warm=8, part=None):
    """USR contre les agrandissements sans historique, sur chaque capture :
    PSNR et scintillement (comme banc_universel), aux niveaux 1 et 2.
    ``part`` = « mesure » : la reserve seule (voir RESERVE)."""
    rows = []
    for path in fichiers(dossier, part):
        header, frames = lire(path)
        if header["images"] <= warm + 1:
            continue
        name = os.path.basename(path)
        for niveau in (1, 2):
            seq = sequence(frames, niveau)
            dsize = (header["largeur"], header["hauteur"])
            methodes = [("lanczos", lambda i, j: universel.lanczos_upscale(
                i, dsize))]
            for net, label in ((None, "USR-U regles"), (network, "USR-U IA")):
                if label.endswith("IA") and network is None:
                    continue
                up = universel.UniversalUpscaler(seq["rsize"], dsize,
                                                 network=net,
                                                 period=seq["period"])
                methodes.append((label, (lambda u: lambda i, j: u.dispatch(
                    i, j))(up)))
            for label, fn in methodes:
                err, fli = [], []
                prev = prev_gt = None
                for f, (img, jit, _) in enumerate(seq["items"]):
                    out = np.clip(fn(img, jit), 0.0, 1.0)
                    gt = seq["gt"][f]
                    if f >= warm:
                        err.append(np.mean((out - gt) ** 2))
                        if prev is not None:
                            fli.append(np.mean(np.abs((out - prev)
                                                      - (gt - prev_gt))))
                    prev, prev_gt = out, gt
                row = {"capture": name, "niveau": niveau, "methode": label,
                       "psnr": float(10 * np.log10(1 / np.mean(err))),
                       "scint": float(np.mean(fli))}
                rows.append(row)
                log("  %-40s niveau %d %-13s PSNR %.2f  scint. %.4f" % (
                    name, niveau, label, row["psnr"], row["scint"]))
    return rows
