"""Le petit reseau de l'upscaler : 10 entrees -> 16 -> 16 -> 2 sorties.

Il ne fabrique pas de pixels. Pour chaque pixel il decide deux choses que
les TAA classiques fixent a la main :

* ``alpha`` : combien croire l'image courante face a l'historique (sortie 0,
  ajoutee au logit de la regle heuristique) ;
* ``beta``  : combien garder l'historique brut plutot que sa version
  recadree dans la boite de couleurs voisine (sortie 1).

482 parametres, ~420 multiplications-additions par pixel : de quoi tenir
sur le GPU de la Xbox Series X sans unites matricielles.

Format binaire (``.bin``) : float32 petit-boutiste, dans cet ordre
W1[16][10], b1[16], W2[16][16], b2[16], W3[2][16], b3[2], puis 2 zeros de
bourrage (484 = 121 float4, la taille du cbuffer du shader).
"""

import json
import os

import numpy as np

from .core import N_FEATURES

HIDDEN = 16
OUTPUTS = 2
N_PARAMS = (N_FEATURES * HIDDEN + HIDDEN + HIDDEN * HIDDEN + HIDDEN
            + HIDDEN * OUTPUTS + OUTPUTS)
N_PADDED = (N_PARAMS + 3) // 4 * 4

FEATURE_NAMES = [
    "alpha_heuristique", "ecart_historique", "recadrage", "contraste_local",
    "desocclusion", "mouvement_log2", "poids_courant", "confiance",
    "ecart_courant", "flou_reechantillonnage",
]


class Network:
    def __init__(self, w1, b1, w2, b2, w3, b3):
        self.w1 = np.asarray(w1, np.float32).reshape(HIDDEN, N_FEATURES)
        self.b1 = np.asarray(b1, np.float32).reshape(HIDDEN)
        self.w2 = np.asarray(w2, np.float32).reshape(HIDDEN, HIDDEN)
        self.b2 = np.asarray(b2, np.float32).reshape(HIDDEN)
        self.w3 = np.asarray(w3, np.float32).reshape(OUTPUTS, HIDDEN)
        self.b3 = np.asarray(b3, np.float32).reshape(OUTPUTS)

    @classmethod
    def zeros(cls):
        """Reseau neutre : alpha = heuristique, beta ~ 0 (historique recadre)."""
        net = cls(np.zeros((HIDDEN, N_FEATURES)), np.zeros(HIDDEN),
                  np.zeros((HIDDEN, HIDDEN)), np.zeros(HIDDEN),
                  np.zeros((OUTPUTS, HIDDEN)), np.zeros(OUTPUTS))
        net.b3[1] = -8.0
        return net

    def forward(self, x):
        h1 = np.maximum(x @ self.w1.T + self.b1, 0.0)
        h2 = np.maximum(h1 @ self.w2.T + self.b2, 0.0)
        return h2 @ self.w3.T + self.b3

    # --- serialisation ---------------------------------------------------

    def flat(self):
        v = np.concatenate([self.w1.ravel(), self.b1, self.w2.ravel(),
                            self.b2, self.w3.ravel(), self.b3])
        return np.concatenate([v, np.zeros(N_PADDED - N_PARAMS)]).astype(
            "<f4")

    @classmethod
    def from_flat(cls, v):
        v = np.asarray(v, np.float32)
        sizes = [HIDDEN * N_FEATURES, HIDDEN, HIDDEN * HIDDEN, HIDDEN,
                 OUTPUTS * HIDDEN, OUTPUTS]
        parts, o = [], 0
        for s in sizes:
            parts.append(v[o:o + s])
            o += s
        return cls(*parts)

    def save(self, path_json, path_bin=None, meta=None):
        doc = {
            "format": "usr-net-1",
            "architecture": [N_FEATURES, HIDDEN, HIDDEN, OUTPUTS],
            "features": FEATURE_NAMES,
            "w1": self.w1.tolist(), "b1": self.b1.tolist(),
            "w2": self.w2.tolist(), "b2": self.b2.tolist(),
            "w3": self.w3.tolist(), "b3": self.b3.tolist(),
            "meta": meta or {},
        }
        with open(path_json, "w", encoding="utf-8") as f:
            json.dump(doc, f, indent=1)
            f.write("\n")
        if path_bin:
            self.flat().tofile(path_bin)

    @classmethod
    def load(cls, path):
        if path.endswith(".bin"):
            return cls.from_flat(np.fromfile(path, "<f4"))
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
        if doc.get("format") != "usr-net-1":
            raise ValueError("format de poids inconnu : %r" % doc.get("format"))
        return cls(doc["w1"], doc["b1"], doc["w2"], doc["b2"], doc["w3"],
                   doc["b3"])

    def to_c_header(self, path, meta=""):
        v = self.flat()
        lines = [
            "// Genere par `python -m usr_ref exporter` -- ne pas editer.",
            "// Poids par defaut du reseau USR (%d parametres). %s" % (
                N_PARAMS, meta),
            "#pragma once",
            "",
            "namespace usr { namespace detail {",
            "",
            "static const unsigned kDefaultWeightCount = %d;" % N_PADDED,
            "alignas(16) static const float kDefaultWeights[%d] = {" %
            N_PADDED,
        ]
        for i in range(0, N_PADDED, 4):
            lines.append("    " + ", ".join(
                "%.9ef" % x if np.isfinite(x) else "0.0f"
                for x in v[i:i + 4]) + ",")
        lines += ["};", "", "}} // namespace usr::detail", ""]
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))


def default_weights_path():
    return os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "weights", "usr_net.json")


def load_default():
    path = default_weights_path()
    return Network.load(path) if os.path.exists(path) else None
