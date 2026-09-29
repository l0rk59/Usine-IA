"""Entrainement du reseau de USR Universel (meme principe que train.py).

Donnees : des « jeux emules » (emul.EmulatedGame) dont on connait la verite
terrain, joues tels que l'emulateur les verrait : image affichee 8 bits,
HUD, pas de vecteurs de mouvement. Deux usages sont melanges :

* niveau 1 : l'emulateur ne touche a rien (pas de jitter) ;
* niveau 2 : l'emulateur injecte un jitter en grille ordonnee sur la scene
  3D (pas sur le HUD), avec ou sans biais de mip-map -1 ;

aux rapports 2 (720p -> 1440p) et 3 (720p -> 4K), sur la scene realiste
(textures filtrees) et sur la scene « brutale » (textures crenelees). Le
mouvement vient toujours de l'estimateur ``flow`` : le reseau apprend a
vivre avec ses erreurs.

Pour chaque pixel on enregistre les 10 caracteristiques et les couleurs en
jeu (historique reprojete, residu interpole, image fraiche), puis on apprend
les deux corrections (reactivite, gain) qui rapprochent le resultat de la
verite, en plusieurs tours (chaque tour rejoue avec le reseau precedent).
"""

import os
import pickle
import time

import numpy as np

from . import core, emul, universel
from .network import HIDDEN, N_FEATURES, Network
from .scene import Scene
from .scene_realiste import RealisticScene
from .train import Trainer, fit, merge

assert N_FEATURES == universel.N_FEATURES

DISPLAY = (384, 216)


def training_specs(rng):
    """Liste de sequences : (nom, fabrique de scene, rapport, niveau, lod)."""
    specs = []

    def realistic(seed, static=False):
        speed = tuple(rng.uniform(-0.02, 0.02, 2))
        ospeed = float(rng.uniform(0.3, 2.0))
        wob = float(rng.uniform(0.0, 0.01))
        return ("real%d" % seed, dict(kind="real", seed=seed, static=static,
                                      camera_speed=speed,
                                      object_speed=ospeed, wobble=wob))

    def brutal(seed):
        speed = tuple(rng.uniform(-0.012, 0.012, 2))
        return ("brut%d" % seed, dict(kind="brut", seed=seed,
                                      camera_speed=speed))

    scenes2 = [realistic(s, static=(s == 3)) for s in range(1, 7)] + [
        brutal(s) for s in (1, 2)]
    scenes3 = [realistic(s, static=(s == 8)) for s in range(7, 10)]
    for ratio, scenes in ((2, scenes2), (3, scenes3)):
        for name, sc in scenes:
            specs.append((name, sc, ratio, 1, 0.0))
            lod = -1.0 if rng.uniform() < 0.6 else 0.0
            specs.append((name, sc, ratio, 2, lod))
    return specs


def make_scene(sc):
    sc = dict(sc)
    kind = sc.pop("kind")
    if kind == "real":
        return RealisticScene(**sc)
    return Scene(**sc)


def render_sequence(spec, frames, cache_dir, log=print):
    """Images (+ verite terrain) d'une sequence ; mis en cache sur disque."""
    name, sc, ratio, level, lod = spec
    rsize = (DISPLAY[0] // ratio, DISPLAY[1] // ratio)
    key = "%s_r%d_n%d_l%g_%d" % (name, ratio, level, lod, frames)
    path = os.path.join(cache_dir, key + ".pkl")
    if os.path.exists(path):
        return load_sequence(path)
    t0 = time.time()
    game = emul.EmulatedGame(make_scene(sc))
    gt_path = os.path.join(cache_dir, "gt_%s_%d.pkl" % (name, frames))
    gts = None
    if os.path.exists(gt_path):
        with open(gt_path, "rb") as f:
            gts = pickle.load(f)
    if level == 2:
        jit, period = universel.jitter_plan(rsize, DISPLAY, "grille")
    else:
        jit, period = universel.jitter_plan(rsize, DISPLAY, "aucun")
    items = []
    new_gts = []
    for f in range(frames):
        j = jit(f)
        img, _, motion = game.frame(float(f), rsize, j, lod_bias=lod,
                                    hud_jitter=(level == 1))
        gt = gts[f] if gts is not None else game.truth(float(f), DISPLAY)
        new_gts.append(np.asarray(gt, np.float32))
        # image 8 bits : stockee telle quelle (exacte, 4 fois plus petite)
        items.append((np.round(img * 255.0).astype(np.uint8), j,
                      motion.astype(np.float16)))
    if gts is None:
        with open(gt_path, "wb") as f:
            pickle.dump(new_gts, f)
    seq = {"spec": spec, "rsize": rsize, "period": period, "items": items,
           "gt_file": os.path.basename(gt_path)}
    with open(path, "wb") as f:
        pickle.dump(seq, f)
    log("  %s : %.0f s" % (key, time.time() - t0))
    return load_sequence(path)


def load_sequence(path):
    """Relit une sequence : images en flottants [0, 1], verite jointe."""
    with open(path, "rb") as f:
        seq = pickle.load(f)
    with open(os.path.join(os.path.dirname(path), seq["gt_file"]),
              "rb") as f:
        seq["gt"] = pickle.load(f)
    seq["items"] = [(img.astype(np.float32) / np.float32(255.0), j,
                     m.astype(np.float32)) for img, j, m in seq["items"]]
    return seq


# --------------------------------------------------------------------------
# Collecte
# --------------------------------------------------------------------------

def collect(seqs, network, per_frame, rng, warmup=2):
    cols = {k: [] for k in ("x", "hr", "u", "fr", "rh", "gh", "g", "dg")}
    for seq in seqs:
        up = universel.UniversalUpscaler(seq["rsize"], DISPLAY,
                                         network=network,
                                         period=seq["period"])
        gt_prev = None
        for f, (img, j, motion) in enumerate(seq["items"]):
            gt = core.rgb_to_ycocg(seq["gt"][f].astype(np.float32))
            _, info = up.dispatch(img, j, return_internals=True)
            if f < warmup:
                gt_prev = gt
                continue
            d_gt = gt - core.sample_catmull_rom(gt_prev, *info["puv"])
            gt_prev = gt
            idx = np.flatnonzero(info["valid"].ravel())
            if idx.size == 0:
                continue
            idx = rng.choice(idx, min(per_frame, idx.size), replace=False)
            cols["x"].append(info["features"].reshape(-1, N_FEATURES)[idx])
            cols["hr"].append(info["hr"].reshape(-1, 3)[idx])
            cols["u"].append(info["upd"].reshape(-1, 3)[idx])
            cols["fr"].append(info["fresh"].reshape(-1, 3)[idx])
            cols["rh"].append(info["react_h"].ravel()[idx])
            cols["gh"].append(info["gain_h"].ravel()[idx])
            cols["g"].append(gt.reshape(-1, 3)[idx])
            cols["dg"].append(d_gt.reshape(-1, 3)[idx])
    return {k: np.concatenate(v).astype(np.float32) for k, v in cols.items()}


def _logit(p):
    p = np.clip(p, 1e-3, 1.0 - 1e-3)
    return np.log(p / (1.0 - p))


class UniversalTrainer(Trainer):
    """Sortie 0 : correction de la reactivite ; sortie 1 : du gain."""

    def __init__(self, rng, mean=None, std=None, stability=1.0):
        super().__init__(rng, mean, std, stability)
        self.p["b3"] = np.zeros(2)

    def forward_out(self, batch, o):
        react = 1.0 / (1.0 + np.exp(-(_logit(batch["rh"]) + o[:, 0])))
        gain = 1.0 / (1.0 + np.exp(-(_logit(batch["gh"]) + o[:, 1])))
        acc = batch["hr"] + batch["u"] * gain[:, None]
        out = acc + (batch["fr"] - acc) * react[:, None]
        return out, acc, react, gain

    def loss_and_grads(self, batch):
        p = self.p
        x = (batch["x"] - self.mean) / self.std
        z1 = x @ p["w1"].T + p["b1"]
        h1 = np.maximum(z1, 0.0)
        z2 = h1 @ p["w2"].T + p["b2"]
        h2 = np.maximum(z2, 0.0)
        o = h2 @ p["w3"].T + p["b3"]
        out, acc, react, gain = self.forward_out(batch, o)
        err = out - batch["g"]
        flick = (out - batch["hr"]) - batch["dg"]
        n = len(x)
        lam = self.stability
        loss = float((np.sum(err * err) + lam * np.sum(flick * flick)) / n)
        d_out = 2.0 * (err + lam * flick) / n
        d_react = np.sum(d_out * (batch["fr"] - acc), axis=1)
        d_acc = d_out * (1.0 - react)[:, None]
        d_gain = np.sum(d_acc * batch["u"], axis=1)
        d_o = np.stack([d_react * react * (1.0 - react),
                        d_gain * gain * (1.0 - gain)], axis=1)
        g_ = {"w3": d_o.T @ h2, "b3": d_o.sum(0)}
        d_z2 = (d_o @ p["w3"]) * (z2 > 0)
        g_["w2"] = d_z2.T @ h1
        g_["b2"] = d_z2.sum(0)
        d_z1 = (d_z2 @ p["w2"]) * (z1 > 0)
        g_["w1"] = d_z1.T @ x
        g_["b1"] = d_z1.sum(0)
        return loss, g_


def baseline_loss(data, stability=1.0):
    """Perte des regles heuristiques seules."""
    acc = data["hr"] + data["u"] * data["gh"][:, None]
    out = acc + (data["fr"] - acc) * data["rh"][:, None]
    flick = (out - data["hr"]) - data["dg"]
    return float(np.mean(np.sum((out - data["g"]) ** 2, axis=1)
                         + stability * np.sum(flick * flick, axis=1)))


def capture_sequences(dossier, log=print):
    """Sequences tirees des captures de vrais jeux (capture_jeu), aux
    niveaux 1 et 2, a la taille d'affichage de l'entrainement seulement."""
    from . import capture_jeu
    seqs = []
    for path in capture_jeu.fichiers(dossier, "entrainement"):
        header, frames = capture_jeu.lire(path)
        if (header["largeur"], header["hauteur"]) != DISPLAY or \
                header["images"] < 4:
            log("  %s ignoree (%dx%d, %d images)" % (
                os.path.basename(path), header["largeur"],
                header["hauteur"], header["images"]))
            continue
        for niveau in (1, 2):
            seqs.append(capture_jeu.sequence(frames, niveau))
    log("  %d sequences de captures" % len(seqs))
    return seqs


def train(cache_dir, frames=24, rounds=3, steps=4000, batch=4096, lr=3e-3,
          per_frame=1200, seed=0, stability=1.0, captures=None, log=print):
    rng = np.random.default_rng(seed)
    t_start = time.time()
    os.makedirs(cache_dir, exist_ok=True)
    specs = training_specs(rng)
    log("Rendu / chargement de %d sequences..." % len(specs))
    seqs = [render_sequence(s, frames, cache_dir, log) for s in specs]
    if captures:
        seqs += capture_sequences(captures, log)
    network, data, trainer = None, None, None
    for r in range(rounds):
        log("Tour %d/%d : collecte avec %s" % (
            r + 1, rounds, "le reseau" if network else "l'heuristique"))
        fresh = collect(seqs, network, per_frame, rng)
        data = fresh if data is None else merge(data, fresh)
        log("  %d exemples ; perte heuristique %.6f" % (
            len(data["x"]), baseline_loss(data, stability)))
        if trainer is None:
            trainer = UniversalTrainer(rng, data["x"].mean(0),
                                       data["x"].std(0) + 1e-3, stability)
        fit(trainer, data, steps, batch, lr, rng, log)
        network = trainer.export()
    log("Entrainement termine en %.0f s" % (time.time() - t_start))
    meta = {"role": "universel", "display_size": list(DISPLAY),
            "sequences": len(seqs), "frames": frames, "rounds": rounds,
            "steps": steps, "stability": stability, "seed": seed,
            "captures": bool(captures),
            "features": universel.FEATURE_NAMES,
            "sorties": ["reactivite (logit)", "gain (logit)"]}
    return network, meta


assert HIDDEN == 16 and Network is not None
