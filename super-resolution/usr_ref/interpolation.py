"""Generation d'images : une image intermediaire entre deux sorties de USR.

Un jeu Xbox 360 tourne le plus souvent a 30 images par seconde. Entre deux
images reelles, on fabrique celle du milieu a partir du flot que USR
Universel vient d'estimer (usr_ref/flow.py) : aucun vecteur du jeu, comme
pour l'agrandissement.

Le flot ``m`` est connu a la resolution de rendu, aux positions de l'image
COURANTE : un point en ``x`` dans l'image courante etait en ``x - m`` dans
la precedente. A l'instant ``t`` (0 : precedente, 1 : courante), le point
qui passe en ``x`` est en ``x + (1 - t) m`` dans la courante et en
``x - t m`` dans la precedente. Le flot est lu une premiere fois en ``x``
puis relu a la position courante estimee : sans cette seconde lecture, le
bord d'un objet rapide est tire avec le mouvement du fond qu'il recouvre.

Deux hypotheses par pixel, departagees par l'accord des deux images :
« suivre le flot » et « rester sur place » (fondu). La seconde sauve ce que
le flot ne sait pas suivre : un neon qui clignote, un ecran qui change.

Le piege mesure (docs/GENERATION.md) : un motif periodique qui defile (un
ecran anime, une grille). Le flot y accroche un decalage d'une periode
entiere, et les deux images recalees S'ACCORDENT sur une reponse fausse --
l'accord ne peut pas le voir. Deux temoins du flot lui-meme le trahissent :
son ecart a ses voisins, et son ecart au flot de l'image precedente lu la
ou le point etait (un mouvement reel varie peu d'une image a l'autre, un
alias saute). Au-dela de SEUIL_FLOT pixels, l'hypothese « flot » est
retiree.

Ou aucune hypothese n'accorde les deux images (desocclusion), on prend
l'image courante recalee seule : un melange a 50 % y montrerait deux objets
fantomes superposes.

Le shader usr_u_interp.hlsl suit cette reference a l'identique.
"""

import numpy as np

from . import core

F32 = np.float32

# Ecart de luminance moyen (3x3, 0..1) entre les deux images recalees :
# echelle de l'accord (poids exp(-(ecart / SIGMA_ACCORD)^2)), et seuil a
# partir duquel on cede a l'image courante (entierement a 2 x SIGMA).
SIGMA_ACCORD = 0.12
# Ecart du flot (pixels de rendu) a ses voisins ou a l'image precedente
# a partir duquel l'hypothese « flot » perd du poids (nulle a 2 x).
SEUIL_FLOT = 2.0
# Poids de l'hypothese « sur place » a accord egal : le flot est prefere.
POIDS_SUR_PLACE = 0.5


def _luma(c):
    return F32(0.25) * c[..., 0] + F32(0.5) * c[..., 1] + \
        F32(0.25) * c[..., 2]


def _nearest(tex, u, v):
    h, w = tex.shape[:2]
    ix = np.clip(np.floor(u * F32(w)).astype(np.int64), 0, w - 1)
    iy = np.clip(np.floor(v * F32(h)).astype(np.int64), 0, h - 1)
    return tex[iy, ix]


def _moyenne3(x):
    h, w = x.shape
    p = np.pad(x, 1, mode="edge")
    acc = np.zeros_like(x)
    for j in range(3):
        for i in range(3):
            acc = acc + p[j:j + h, i:i + w]
    return (acc / F32(9.0)).astype(F32)


def doute_du_flot(mouvement, mouvement_prec=None):
    """Par pixel de rendu : max(ecart du flot a ses 8 voisins, ecart au flot
    precedent lu la ou le point etait), en pixels de rendu."""
    h, w = mouvement.shape[:2]
    p = np.pad(mouvement, ((1, 1), (1, 1), (0, 0)), mode="edge")
    voisins = np.zeros((h, w), F32)
    for j in range(3):
        for i in range(3):
            voisins = np.maximum(voisins, np.abs(
                p[j:j + h, i:i + w] - mouvement).max(-1))
    if mouvement_prec is None:
        return voisins
    oy, ox = np.mgrid[0:h, 0:w]
    u = (ox.astype(F32) + F32(0.5) - mouvement[..., 0]) / F32(w)
    v = (oy.astype(F32) + F32(0.5) - mouvement[..., 1]) / F32(h)
    temps = np.abs(_nearest(mouvement_prec, u, v) - mouvement).max(-1)
    return np.maximum(voisins, temps).astype(F32)


def _hypothese(prec, cour, u, v, m, t):
    uc = u + (F32(1.0) - t) * m[..., 0]
    vc = v + (F32(1.0) - t) * m[..., 1]
    up = u - t * m[..., 0]
    vp = v - t * m[..., 1]
    cc = core.sample_bilinear(cour, uc, vc).astype(F32)
    cp = core.sample_bilinear(prec, up, vp).astype(F32)
    dedans = (up >= 0.0) & (up <= 1.0) & (vp >= 0.0) & (vp <= 1.0)
    return cc, cp, dedans, np.abs(_luma(cc) - _luma(cp)).astype(F32)


def interpoler(prec, cour, mouvement, mouvement_prec=None, t=0.5):
    """Image a l'instant ``t`` entre ``prec`` et ``cour`` (h, w, 3, [0, 1],
    resolution d'affichage). ``mouvement`` (rh, rw, 2) : flot de l'image
    courante en pixels de rendu ; ``mouvement_prec`` : celui de l'image
    precedente (None apres une coupure). Renvoie (image, poids de
    l'hypothese « flot », part de l'image courante seule)."""
    dh, dw = cour.shape[:2]
    rh, rw = mouvement.shape[:2]
    oy, ox = np.mgrid[0:dh, 0:dw]
    u = (ox.astype(F32) + F32(0.5)) / F32(dw)
    v = (oy.astype(F32) + F32(0.5)) / F32(dh)
    t = F32(t)
    echelle = np.array([rw, rh], F32)

    m0 = _nearest(mouvement, u, v) / echelle
    uc0 = u + (F32(1.0) - t) * m0[..., 0]
    vc0 = v + (F32(1.0) - t) * m0[..., 1]
    m1 = _nearest(mouvement, uc0, vc0) / echelle
    doute = np.clip(
        (_nearest(doute_du_flot(mouvement, mouvement_prec), uc0, vc0)
         - F32(SEUIL_FLOT)) / F32(SEUIL_FLOT), 0.0, 1.0).astype(F32)

    cc1, cp1, in1, e1 = _hypothese(prec, cour, u, v, m1, t)
    cc0, cp0, _, e0 = _hypothese(prec, cour, u, v, np.zeros_like(m1), t)
    # Accord moyen sur 3x3 : un pixel isole qui s'accorde par hasard ne
    # decide pas seul.
    e1 = np.where(in1, _moyenne3(e1), F32(1.0))
    e0 = _moyenne3(e0)
    s = F32(SIGMA_ACCORD)
    w1 = np.exp(-(e1 / s) ** 2) * (F32(1.0) - doute)
    w0 = F32(POIDS_SUR_PLACE) * np.exp(-(e0 / s) ** 2)
    a = (w1 / (w1 + w0 + F32(1e-6))).astype(F32)
    fondu = cp0 + (cc0 - cp0) * t
    suivi = cp1 + (cc1 - cp1) * t
    melange = fondu + (suivi - fondu) * a[..., None]

    # Personne n'accorde les deux images : l'image courante recalee seule --
    # sauf si le flot est lui-meme douteux, ou le fondu reste le moins faux.
    douteux = doute > F32(0.5)
    meilleur = np.where(douteux, e0, np.minimum(e1, e0))
    repli = np.clip((meilleur - s) / s, 0.0, 1.0).astype(F32)
    seule = np.where(douteux[..., None], fondu, cc1)
    out = melange + (seule - melange) * repli[..., None]
    return np.clip(out, 0.0, 1.0).astype(F32), a, repli
