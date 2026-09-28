"""Entrainement du reseau USR, sans PyTorch : NumPy et une retropropagation
ecrite a la main (le reseau n'a que 482 parametres).

Principe : on fait tourner l'upscaler sur des scenes dont on connait la
verite terrain, on enregistre pour chaque pixel ses 10 caracteristiques et
les couleurs en jeu (courante, historique brut, historique recadre), puis
on apprend les ``alpha`` / ``beta`` qui rapprochent le resultat de la
verite. Comme l'historique depend du reseau lui-meme, on recommence en
plusieurs tours : chaque tour collecte ses donnees avec le reseau du tour
precedent (les erreurs qu'il provoque deviennent des exemples).
"""

import time

import numpy as np

from . import core
from .network import HIDDEN, N_FEATURES, OUTPUTS, Network
from .scene import Scene


# --------------------------------------------------------------------------
# Donnees
# --------------------------------------------------------------------------

def training_scenes(n_seeds, rng):
    scenes = []
    for seed in range(1, n_seeds + 1):
        speed = rng.uniform(-0.012, 0.012, 2)
        scenes.append(Scene(seed=seed, camera_speed=speed,
                            object_speed=rng.uniform(0.5, 2.5)))
        scenes.append(Scene(seed=seed + 1000, static=True))
    return scenes


def render_sequences(scenes, display_size, modes, frames, log=print):
    """Pre-calcule les images (le plus long) une fois pour tous les tours."""
    seqs = []
    for mode in modes:
        rsize = core.render_size(display_size, mode)
        phases = core.jitter_phase_count(rsize[0], display_size[0])
        for i, scene in enumerate(scenes):
            t0 = 50.0 * i
            items = []
            for f in range(frames):
                jitter = core.jitter_offset(f, phases)
                color, invz, motion = scene.render(t0 + f, rsize, jitter)
                gt = scene.ground_truth(t0 + f, display_size)
                items.append((color, invz, motion, jitter,
                              core.tonemap(gt)))
            seqs.append((rsize, items))
        log("  images rendues : mode %s (%d sequences)" % (mode, len(scenes)))
    return seqs


def collect(seqs, display_size, network, per_frame, rng):
    cols = {k: [] for k in ("x", "c", "hr", "hc", "ah", "g", "dg")}
    for rsize, items in seqs:
        up = core.Upscaler(rsize, display_size, network=network)
        gt_prev = None
        for f, (color, invz, motion, jitter, gt_t) in enumerate(items):
            _, info = up.dispatch(color, invz, motion, jitter,
                                  return_internals=True)
            if f < 2:
                gt_prev = gt_t
                continue
            # Variation "vraie" de l'image, suivie le long du mouvement :
            # ce que la sortie a le droit de changer d'une image a l'autre.
            d_gt = gt_t - core.sample_catmull_rom(gt_prev, *info["puv"])
            gt_prev = gt_t
            idx = np.flatnonzero(info["valid"].ravel())
            if idx.size == 0:
                continue
            idx = rng.choice(idx, min(per_frame, idx.size), replace=False)
            cols["x"].append(info["features"].reshape(-1, N_FEATURES)[idx])
            cols["c"].append(info["cur"].reshape(-1, 3)[idx])
            cols["hr"].append(info["h_raw"].reshape(-1, 3)[idx])
            cols["hc"].append(info["h_clip"].reshape(-1, 3)[idx])
            cols["ah"].append(info["alpha_heur"].ravel()[idx])
            cols["g"].append(gt_t.reshape(-1, 3)[idx])
            cols["dg"].append(d_gt.reshape(-1, 3)[idx])
    return {k: np.concatenate(v).astype(np.float32) for k, v in cols.items()}


def merge(a, b):
    return {k: np.concatenate([a[k], b[k]]) for k in a}


# --------------------------------------------------------------------------
# Modele differentiable
# --------------------------------------------------------------------------

class Trainer:
    """``stability`` pondere un second terme de perte : la variation de la
    sortie d'une image a l'autre doit suivre celle de la verite terrain.
    Sans lui, le reseau gagne en finesse mais scintille davantage."""

    def __init__(self, rng, mean=None, std=None, stability=1.0):
        self.stability = stability
        he1 = np.sqrt(2.0 / N_FEATURES)
        he2 = np.sqrt(2.0 / HIDDEN)
        self.p = {
            "w1": rng.normal(0, he1, (HIDDEN, N_FEATURES)),
            "b1": np.zeros(HIDDEN),
            "w2": rng.normal(0, he2, (HIDDEN, HIDDEN)),
            "b2": np.zeros(HIDDEN),
            "w3": np.zeros((OUTPUTS, HIDDEN)),
            "b3": np.array([0.0, -2.0]),
        }
        self.mean = np.zeros(N_FEATURES) if mean is None else mean
        self.std = np.ones(N_FEATURES) if std is None else std
        self.m = {k: np.zeros_like(v) for k, v in self.p.items()}
        self.v = {k: np.zeros_like(v) for k, v in self.p.items()}
        self.step_count = 0

    def loss_and_grads(self, batch):
        p = self.p
        x = (batch["x"] - self.mean) / self.std
        z1 = x @ p["w1"].T + p["b1"]
        h1 = np.maximum(z1, 0.0)
        z2 = h1 @ p["w2"].T + p["b2"]
        h2 = np.maximum(z2, 0.0)
        o = h2 @ p["w3"].T + p["b3"]

        a = np.clip(batch["ah"], 1e-4, 1.0 - 1e-4)
        alpha = 1.0 / (1.0 + np.exp(-(np.log(a / (1.0 - a)) + o[:, 0])))
        beta = 1.0 / (1.0 + np.exp(-o[:, 1]))
        hr, hc, c, g = batch["hr"], batch["hc"], batch["c"], batch["g"]
        h = hc + (hr - hc) * beta[:, None]
        out = h + (c - h) * alpha[:, None]
        err = out - g
        flick = (out - hr) - batch["dg"]
        n = len(x)
        lam = self.stability
        loss = float((np.sum(err * err) + lam * np.sum(flick * flick)) / n)

        d_out = 2.0 * (err + lam * flick) / n
        d_alpha = np.sum(d_out * (c - h), axis=1)
        d_h = d_out * (1.0 - alpha)[:, None]
        d_beta = np.sum(d_h * (hr - hc), axis=1)
        d_o = np.stack([d_alpha * alpha * (1.0 - alpha),
                        d_beta * beta * (1.0 - beta)], axis=1)
        g_ = {"w3": d_o.T @ h2, "b3": d_o.sum(0)}
        d_z2 = (d_o @ p["w3"]) * (z2 > 0)
        g_["w2"] = d_z2.T @ h1
        g_["b2"] = d_z2.sum(0)
        d_z1 = (d_z2 @ p["w2"]) * (z1 > 0)
        g_["w1"] = d_z1.T @ x
        g_["b1"] = d_z1.sum(0)
        return loss, g_

    def adam(self, grads, lr, b1=0.9, b2=0.999, eps=1e-8):
        self.step_count += 1
        for k in self.p:
            self.m[k] = b1 * self.m[k] + (1 - b1) * grads[k]
            self.v[k] = b2 * self.v[k] + (1 - b2) * grads[k] ** 2
            mh = self.m[k] / (1 - b1 ** self.step_count)
            vh = self.v[k] / (1 - b2 ** self.step_count)
            self.p[k] = self.p[k] - lr * mh / (np.sqrt(vh) + eps)

    def export(self):
        """Replie la normalisation des entrees dans la premiere couche : le
        shader recoit les caracteristiques brutes."""
        p = self.p
        w1 = p["w1"] / self.std[None, :]
        b1 = p["b1"] - w1 @ self.mean
        return Network(w1, b1, p["w2"], p["b2"], p["w3"], p["b3"])


def fit(trainer, data, steps, batch, lr, rng, log=print):
    n = len(data["x"])
    for s in range(steps):
        idx = rng.integers(0, n, batch)
        loss, grads = trainer.loss_and_grads({k: v[idx] for k, v in
                                              data.items()})
        cur_lr = lr * (0.1 ** (s / max(steps, 1)))
        trainer.adam(grads, cur_lr)
        if s % 500 == 0 or s == steps - 1:
            log("    pas %5d  perte %.6f" % (s, loss))


def baseline_loss(data, stability=1.0):
    """Perte de la regle heuristique seule (alpha heuristique, recadre)."""
    a = data["ah"][:, None]
    out = data["hc"] + (data["c"] - data["hc"]) * a
    flick = (out - data["hr"]) - data["dg"]
    return float(np.mean(np.sum((out - data["g"]) ** 2, axis=1)
                         + stability * np.sum(flick * flick, axis=1)))


# --------------------------------------------------------------------------
# Entree principale
# --------------------------------------------------------------------------

def train(display_size=(256, 144), n_seeds=6, frames=24, rounds=3,
          steps=3000, batch=4096, lr=3e-3, per_frame=1500, seed=0,
          modes=("performance", "qualite"), stability=1.0, seqs=None,
          log=print):
    rng = np.random.default_rng(seed)
    t_start = time.time()
    if seqs is None:
        log("Rendu des sequences d'entrainement...")
        seqs = render_sequences(training_scenes(n_seeds, rng), display_size,
                                modes, frames, log)

    network, data, trainer = None, None, None
    for r in range(rounds):
        log("Tour %d/%d : collecte avec %s" % (
            r + 1, rounds, "le reseau" if network else "l'heuristique"))
        fresh = collect(seqs, display_size, network, per_frame, rng)
        data = fresh if data is None else merge(data, fresh)
        log("  %d exemples ; perte heuristique %.6f" % (
            len(data["x"]), baseline_loss(data, stability)))
        if trainer is None:
            trainer = Trainer(rng, data["x"].mean(0),
                              data["x"].std(0) + 1e-3, stability)
        fit(trainer, data, steps, batch, lr, rng, log)
        network = trainer.export()
    log("Entrainement termine en %.0f s" % (time.time() - t_start))
    return network, {"display_size": list(display_size),
                     "modes": list(modes), "sequences": len(seqs),
                     "frames": frames, "rounds": rounds, "steps": steps,
                     "stability": stability, "seed": seed}
