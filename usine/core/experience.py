"""A/B testing des titres, couvertures, accroches et prix.

Le piege de ce genre d'outil est de designer un gagnant des qu'une variante
prend la tete. Avec 40 visiteurs, l'ecart observe entre deux titres est presque
toujours du bruit : un outil qui annonce « B gagne » dans ces conditions
fabrique de la fausse certitude, et fait prendre des decisions sur du vent.

Ce module fait l'inverse. Il calcule la probabilite reelle que chaque variante
soit la meilleure, refuse de conclure tant que cette probabilite n'est pas
franche, et dit combien d'observations il faudrait encore.

Methode : modele beta-binomial. Chaque variante a une posterieure
Beta(1 + succes, 1 + echecs) — l'a priori uniforme signifie « je ne sais rien
avant de mesurer ». On tire ensuite ces posterieures pour obtenir :
  - P(cette variante est la meilleure), toutes comparees ensemble ;
  - la perte esperee : ce qu'on risque de perdre en choisissant celle-ci.

Le tirage conjoint evite le piege des comparaisons multiples : avec cinq
variantes, comparer deux a deux gonfle mecaniquement les chances de trouver
un « gagnant » qui n'existe pas.
"""

from __future__ import annotations

import json
import math
import random
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import store

SCHEMA = """
CREATE TABLE IF NOT EXISTS experiences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    produit_id TEXT,
    titre TEXT NOT NULL,
    sujet TEXT NOT NULL DEFAULT 'titre',
    objectif TEXT NOT NULL DEFAULT 'ventes',
    statut TEXT NOT NULL DEFAULT 'ouverte',
    gagnante INTEGER,
    note TEXT,
    cree_le REAL NOT NULL,
    maj_le REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS variantes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    experience_id INTEGER NOT NULL,
    etiquette TEXT NOT NULL,
    contenu TEXT NOT NULL,
    fichier TEXT,
    meta TEXT NOT NULL DEFAULT '{}',
    debut TEXT,
    fin TEXT,
    cree_le REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_variantes_exp ON variantes(experience_id);
CREATE TABLE IF NOT EXISTS observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    variante_id INTEGER NOT NULL,
    vues INTEGER NOT NULL DEFAULT 0,
    actions INTEGER NOT NULL DEFAULT 0,
    note TEXT,
    ts REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_observations_var ON observations(variante_id);
"""

SUJETS = ("titre", "couverture", "accroche", "prix")
OBJECTIFS = {"clics": "clics sur la fiche", "ventes": "achats"}

# Seuils de decision. Volontairement severes : le cout d'un faux gagnant est
# de refaire une couverture pour rien, plus la conviction durable d'avoir
# trouve « ce qui marche ».
CERTITUDE_GAGNANT = 0.95
CERTITUDE_TENDANCE = 0.80
PERTE_ACCEPTABLE = 0.005      # 0,5 point de taux de conversion
MINIMUM_ACTIONS = 25          # en dessous, aucune conclusion n'est publiee

_pret = False


def _assurer() -> None:
    global _pret
    if not _pret:
        connexion = store.connect()
        connexion.executescript(SCHEMA)
        # Les tables d'experience naissent a la demande : si elles existaient
        # deja avant l'ajout des colonnes de periode, le script ci-dessus ne
        # les a pas touchees.
        store._ajouter_colonnes(connexion, "variantes",
                                (("debut", "TEXT"), ("fin", "TEXT")))
        _pret = True


# --------------------------------------------------------------------------
# Statistiques
# --------------------------------------------------------------------------


def _lbeta(a: float, b: float) -> float:
    return math.lgamma(a) + math.lgamma(b) - math.lgamma(a + b)


def probabilite_superieure(succes_a: int, essais_a: int,
                           succes_b: int, essais_b: int) -> float:
    """P(taux de B > taux de A), formule exacte pour un a priori uniforme.

    Sert de reference pour verifier le tirage aleatoire : deux methodes
    independantes qui concordent valent mieux qu'une seule qu'on croit sur
    parole.
    """
    alpha_a, beta_a = 1 + succes_a, 1 + max(0, essais_a - succes_a)
    alpha_b, beta_b = 1 + succes_b, 1 + max(0, essais_b - succes_b)
    total = 0.0
    reference = _lbeta(alpha_a, beta_a)
    for i in range(int(alpha_b)):
        total += math.exp(
            _lbeta(alpha_a + i, beta_a + beta_b)
            - math.log(beta_b + i)
            - _lbeta(1 + i, beta_b)
            - reference
        )
    return min(1.0, max(0.0, total))


def _tirer_beta(alpha: float, beta: float, alea: random.Random) -> float:
    """Tirage Beta sans dependance : rapport de deux tirages Gamma."""
    x = alea.gammavariate(alpha, 1.0)
    y = alea.gammavariate(beta, 1.0)
    return x / (x + y) if (x + y) else 0.0


def comparer(
    mesures: Sequence[Tuple[int, int]],
    tirages: int = 40000,
    graine: int = 20260911,
) -> Dict[str, Any]:
    """Compare N variantes ensemble. `mesures` = [(actions, vues), ...].

    Renvoie, pour chacune : le taux observe, l'intervalle credible a 90 %,
    la probabilite d'etre la meilleure, et la perte esperee si on la choisit.

    Le tirage est graine : deux executions sur les memes donnees donnent le
    meme resultat. Un verdict qui changerait d'un appel a l'autre serait
    impossible a defendre.
    """
    if not mesures:
        return {"variantes": [], "meilleure": None}

    alea = random.Random(graine)
    posterieures = [
        (1 + actions, 1 + max(0, vues - actions)) for actions, vues in mesures
    ]
    nombre = len(posterieures)
    victoires = [0] * nombre
    echantillons: List[List[float]] = [[] for _ in range(nombre)]
    perte = [0.0] * nombre

    for _ in range(tirages):
        tirage = [_tirer_beta(a, b, alea) for a, b in posterieures]
        meilleur = max(tirage)
        victoires[tirage.index(meilleur)] += 1
        for index, valeur in enumerate(tirage):
            echantillons[index].append(valeur)
            perte[index] += meilleur - valeur

    resultats = []
    for index, (actions, vues) in enumerate(mesures):
        serie = sorted(echantillons[index])
        resultats.append({
            "index": index,
            "actions": actions,
            "vues": vues,
            "taux": (actions / vues) if vues else 0.0,
            "taux_median": serie[len(serie) // 2],
            "bas": serie[int(len(serie) * 0.05)],
            "haut": serie[int(len(serie) * 0.95)],
            "probabilite_meilleure": victoires[index] / tirages,
            "perte_esperee": perte[index] / tirages,
        })
    meilleure = max(resultats, key=lambda r: r["probabilite_meilleure"])
    return {"variantes": resultats, "meilleure": meilleure["index"],
            "tirages": tirages}


# --------------------------------------------------------------------------
# Comparer des rythmes de vente, quand on n'a pas les vues
# --------------------------------------------------------------------------
#
# Le modele beta-binomial ci-dessus compare des TAUX : il lui faut des vues.
# Une place de marche les donne, mais seulement a l'ecran, et il faut aller
# les relever a la main.
#
# Ce qu'un vendeur possede sans effort, en revanche, c'est le nombre de
# ventes et la duree pendant laquelle chaque variante etait en ligne. Comparer
# « 7 ventes en 14 jours » a « 4 ventes en 12 jours » n'est pas un probleme
# binomial : il n'y a pas d'essais, il y a un comptage sur une duree. Le
# modele qui convient est gamma-poisson.
#
# La loi a priori est Gamma(1, 0) : plate sur le rythme, et la loi a
# posteriori Gamma(1 + ventes, duree) reste propre des que la duree est non
# nulle. Sa forme entiere permet de verifier le tirage aleatoire contre une
# formule exacte, comme pour le beta-binomial.


def probabilite_rythme_superieur(ventes_a: int, jours_a: float,
                                 ventes_b: int, jours_b: float) -> float:
    """P(rythme A > rythme B), exactement.

    X ~ Gamma(a, taux p), Y ~ Gamma(b, taux q) :
        P(X > Y) = somme sur j < a de  G(b+j)/(G(b) j!) * q^b p^j / (p+q)^(b+j)
    """
    if jours_a <= 0 or jours_b <= 0:
        return 0.5
    a, p = 1 + max(0, int(ventes_a)), float(jours_a)
    b, q = 1 + max(0, int(ventes_b)), float(jours_b)
    total = 0.0
    for j in range(a):
        terme = (math.lgamma(b + j) - math.lgamma(b) - math.lgamma(j + 1)
                 + b * math.log(q) + j * math.log(p)
                 - (b + j) * math.log(p + q))
        total += math.exp(terme)
    return min(1.0, max(0.0, total))


def comparer_rythmes(
    mesures: Sequence[Tuple[int, float]],
    tirages: int = 40000,
    graine: int = 20260911,
    etiquettes: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Compare N variantes sur leur rythme. `mesures` = [(ventes, jours), ...].

    Meme discipline que `comparer` : un tirage CONJOINT, graine, et des
    pertes esperees — comparer les variantes deux a deux ferait dire a
    plusieurs comparaisons ce qu'aucune ne dit seule.
    """
    if not mesures:
        return {"variantes": [], "meilleure": None}
    # Une duree nulle n'est pas une petite duree : c'est une absence de
    # mesure. La ramener a 1e-6 donnait a une variante sans donnees un
    # rythme immense, donc la victoire quasi certaine. Elle est ecartee.
    # Les etiquettes suivent le filtrage. Sans elles, l'appelant qui ecarte
    # une variante sans periode voyait le verdict annoncer « variante B »
    # pour ce que le tableau juste au-dessus appelait C : la position dans
    # la liste filtree n'est pas la lettre de la variante.
    paires = [(v, j, (etiquettes[i] if etiquettes and i < len(etiquettes)
                      else _etiquette(i)))
              for i, (v, j) in enumerate(mesures)]
    paires = [t for t in paires if float(t[1]) > 0]
    mesures = [(v, j) for v, j, _ in paires]
    noms = [nom for _, _, nom in paires]
    if not mesures:
        return {"variantes": [], "meilleure": None, "modele": "gamma-poisson"}
    alea = random.Random(graine)
    posterieures = [(1 + max(0, int(ventes)), float(jours))
                    for ventes, jours in mesures]
    nombre = len(posterieures)
    victoires = [0] * nombre
    echantillons: List[List[float]] = [[] for _ in range(nombre)]
    perte = [0.0] * nombre

    for _ in range(tirages):
        # gammavariate prend une ECHELLE : l'inverse du taux.
        tirage = [alea.gammavariate(forme, 1.0 / duree)
                  for forme, duree in posterieures]
        meilleur = max(tirage)
        victoires[tirage.index(meilleur)] += 1
        for index, valeur in enumerate(tirage):
            echantillons[index].append(valeur)
            perte[index] += meilleur - valeur

    resultats = []
    for index, (ventes, jours) in enumerate(mesures):
        serie = sorted(echantillons[index])
        resultats.append({
            "index": index, "etiquette": noms[index],
            "ventes": int(ventes), "jours": round(jours, 1),
            "rythme": (ventes / jours) if jours else 0.0,
            "rythme_median": serie[len(serie) // 2],
            "bas": serie[int(len(serie) * 0.05)],
            "haut": serie[int(len(serie) * 0.95)],
            "probabilite_meilleure": victoires[index] / tirages,
            "perte_esperee": perte[index] / tirages,
        })
    meilleure = max(resultats, key=lambda r: r["probabilite_meilleure"])
    return {"variantes": resultats, "meilleure": meilleure["index"],
            "tirages": tirages, "modele": "gamma-poisson"}


def observations_necessaires(taux: float, effet_relatif: float = 0.20) -> int:
    """Ordre de grandeur du nombre de vues par variante pour trancher.

    Approximation classique pour 80 % de puissance et 95 % de confiance. Ce
    n'est pas une garantie : c'est la pour montrer l'echelle reelle, souvent
    des milliers de vues, la ou l'intuition dit « une centaine suffira ».
    """
    taux = min(max(taux, 0.001), 0.999)
    delta = taux * effet_relatif
    if delta <= 0:
        return 0
    return int(math.ceil(16.0 * taux * (1 - taux) / (delta ** 2)))


def verdict_rythme(comparaison: Dict[str, Any],
                   minimum_ventes: int = MINIMUM_ACTIONS) -> Dict[str, Any]:
    """Conclusion sur des rythmes de vente, avec la meme severite.

    Le seuil porte sur le nombre de VENTES, pas sur le nombre de jours : dix
    jours d'exposition sans vente ne renseignent sur rien, et laisser le
    temps tenir lieu de preuve serait le principal piege de ce modele.
    """
    variantes = comparaison.get("variantes") or []
    if not variantes:
        return {"etat": "vide", "message": "Aucune variante."}
    total_ventes = sum(v["ventes"] for v in variantes)
    total_jours = sum(v["jours"] for v in variantes)
    meilleure = variantes[comparaison["meilleure"]]

    if total_jours <= 0:
        return {"etat": "sans_donnees",
                "message": "Aucune periode de mise en ligne renseignee. "
                           "« usine ab periode <variante> --du ... --au ... »"}
    if total_ventes < minimum_ventes:
        return {
            "etat": "insuffisant",
            "tete": meilleure["index"],
            "manque": minimum_ventes - total_ventes,
            "message": "{} vente(s) sur {:.0f} jours d'exposition : trop peu "
                       "pour conclure. En dessous de {}, l'ecart de rythme est "
                       "du bruit.".format(total_ventes, total_jours,
                                          minimum_ventes),
        }
    if (meilleure["probabilite_meilleure"] >= CERTITUDE_GAGNANT
            and meilleure["perte_esperee"] <= PERTE_ACCEPTABLE):
        return {
            "etat": "gagnant", "gagnante": meilleure["index"],
            "certitude": meilleure["probabilite_meilleure"],
            "message": "Variante {} gagnante : {:.0f} % de chances d'avoir le "
                       "meilleur rythme ({:.2f} vente/jour contre {:.2f}).".format(
                           meilleure.get("etiquette")
                           or _etiquette(meilleure["index"]),
                           meilleure["probabilite_meilleure"] * 100,
                           meilleure["rythme"],
                           max((v["rythme"] for v in variantes
                                if v["index"] != meilleure["index"]), default=0.0)),
        }
    if meilleure["probabilite_meilleure"] >= CERTITUDE_TENDANCE:
        return {
            "etat": "tendance", "tete": meilleure["index"],
            "certitude": meilleure["probabilite_meilleure"],
            "message": "Variante {} en tete ({:.0f} %), sans certitude. "
                       "Laissez tourner.".format(
                           meilleure.get("etiquette")
                           or _etiquette(meilleure["index"]),
                           meilleure["probabilite_meilleure"] * 100),
        }
    return {
        "etat": "indecis", "tete": meilleure["index"],
        "certitude": meilleure["probabilite_meilleure"],
        "message": "Aucune variante ne se detache ({:.0f} % pour la mieux "
                   "placee). L'ecart de rythme observe ne dit rien.".format(
                       meilleure["probabilite_meilleure"] * 100),
    }


def verdict(comparaison: Dict[str, Any],
            minimum_actions: int = MINIMUM_ACTIONS) -> Dict[str, Any]:
    """Conclusion honnete : gagnant, tendance, ou « on ne sait pas encore »."""
    variantes = comparaison.get("variantes") or []
    if not variantes:
        return {"etat": "vide", "message": "Aucune variante."}

    total_actions = sum(v["actions"] for v in variantes)
    total_vues = sum(v["vues"] for v in variantes)
    meilleure = variantes[comparaison["meilleure"]]
    taux_moyen = (total_actions / total_vues) if total_vues else 0.0
    besoin = observations_necessaires(taux_moyen or 0.02)

    if total_vues == 0:
        return {
            "etat": "sans_donnees",
            "message": "Aucune observation enregistree. Publiez les variantes, "
                       "puis reportez les chiffres avec « usine ab observer ».",
            "besoin_par_variante": besoin,
        }

    if total_actions < minimum_actions:
        return {
            "etat": "insuffisant",
            "message": "{} action(s) au total : trop peu pour conclure quoi que "
                       "ce soit. En dessous de {}, l'ecart observe est du bruit."
                       .format(total_actions, minimum_actions),
            "manque": minimum_actions - total_actions,
            "besoin_par_variante": besoin,
            "tete": meilleure["index"],
        }

    if (meilleure["probabilite_meilleure"] >= CERTITUDE_GAGNANT
            and meilleure["perte_esperee"] <= PERTE_ACCEPTABLE):
        return {
            "etat": "gagnant",
            "gagnante": meilleure["index"],
            "certitude": meilleure["probabilite_meilleure"],
            "perte_esperee": meilleure["perte_esperee"],
            "message": "Variante {} gagnante : {:.0f} % de chances d'etre la "
                       "meilleure, risque residuel {:.2f} point.".format(
                           _etiquette(meilleure["index"]),
                           meilleure["probabilite_meilleure"] * 100,
                           meilleure["perte_esperee"] * 100),
        }

    if meilleure["probabilite_meilleure"] >= CERTITUDE_TENDANCE:
        return {
            "etat": "tendance",
            "tete": meilleure["index"],
            "certitude": meilleure["probabilite_meilleure"],
            "besoin_par_variante": besoin,
            "message": "Variante {} en tete ({:.0f} %), mais pas assez pour "
                       "trancher. Continuez : il faudrait de l'ordre de {} vues "
                       "par variante.".format(
                           _etiquette(meilleure["index"]),
                           meilleure["probabilite_meilleure"] * 100, besoin),
        }

    return {
        "etat": "indecis",
        "tete": meilleure["index"],
        "certitude": meilleure["probabilite_meilleure"],
        "besoin_par_variante": besoin,
        "message": "Aucune variante ne se detache ({:.0f} % pour la mieux "
                   "placee). Gardez celle que vous preferez : sur ces donnees, "
                   "le choix n'a pas d'effet mesurable.".format(
                       meilleure["probabilite_meilleure"] * 100),
    }


def _etiquette(index: int) -> str:
    return chr(ord("A") + index) if 0 <= index < 26 else str(index + 1)


# --------------------------------------------------------------------------
# Persistance
# --------------------------------------------------------------------------


def creer(titre: str, sujet: str = "titre", objectif: str = "ventes",
          produit_id: str = "") -> int:
    _assurer()
    if sujet not in SUJETS:
        raise ValueError("sujet inconnu : {}".format(sujet))
    if objectif not in OBJECTIFS:
        raise ValueError("objectif inconnu : {}".format(objectif))
    maintenant = time.time()
    with store.cursor() as cur:
        cur.execute(
            "INSERT INTO experiences(produit_id, titre, sujet, objectif, statut,"
            " cree_le, maj_le) VALUES (?,?,?,?,'ouverte',?,?)",
            (produit_id, titre, sujet, objectif, maintenant, maintenant),
        )
        return int(cur.lastrowid)


def ajouter_variante(experience_id: int, contenu: str, fichier: str = "",
                     meta: Optional[Dict[str, Any]] = None) -> int:
    _assurer()
    with store.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM variantes WHERE experience_id=?",
                    (experience_id,))
        etiquette = _etiquette(int(cur.fetchone()[0]))
        cur.execute(
            "INSERT INTO variantes(experience_id, etiquette, contenu, fichier,"
            " meta, cree_le) VALUES (?,?,?,?,?,?)",
            (experience_id, etiquette, contenu, fichier,
             json.dumps(meta or {}, ensure_ascii=False), time.time()),
        )
        return int(cur.lastrowid)


def observer(variante_id: int, vues: int = 0, actions: int = 0,
             note: str = "") -> None:
    """Ajoute une observation. Les chiffres s'additionnent aux precedents."""
    _assurer()
    if vues < 0 or actions < 0:
        raise ValueError("les chiffres ne peuvent pas etre negatifs")
    if actions > vues:
        raise ValueError(
            "plus d'actions ({}) que de vues ({}) : verifiez la saisie".format(
                actions, vues))
    with store.cursor() as cur:
        cur.execute(
            "INSERT INTO observations(variante_id, vues, actions, note, ts)"
            " VALUES (?,?,?,?,?)",
            (variante_id, vues, actions, note[:200], time.time()),
        )


def fixer_periode(variante_id: int, debut: str, fin: str = "") -> bool:
    """Note quand une variante etait en ligne. Sans cela, aucune vente ne
    peut lui etre attribuee."""
    _assurer()
    if not debut:
        raise ValueError("une periode a besoin d'une date de debut (--du)")
    for valeur in (debut, fin):
        if valeur and not re.match(r"^\d{4}-\d{2}-\d{2}$", valeur):
            raise ValueError("date attendue au format AAAA-MM-JJ : " + valeur)
    if fin and debut and fin < debut:
        raise ValueError("la fin precede le debut")
    with store.cursor() as cur:
        cur.execute("UPDATE variantes SET debut=?, fin=? WHERE id=?",
                    (debut or None, fin or None, variante_id))
        return cur.rowcount > 0


def mesures_reelles(experience_id: int) -> Dict[str, Any]:
    """Ventes reellement encaissees pendant la periode de chaque variante.

    C'est le remplacement du chiffre saisi a la main. Les vues, elles, ne
    sont pas recuperables : aucune place de marche ne les met dans son export
    de ventes. L'usine ne les invente donc pas — elle compte ce qu'elle a, et
    dit ce qui lui manque.

    Le test est SEQUENTIEL, et ce n'est pas un detail : les variantes n'ont
    pas ete exposees en meme temps. Une semaine de vacances scolaires ou un
    partage inattendu se confond avec l'effet du titre, et aucun calcul ne
    repare cela.
    """
    _assurer()
    fiche = lire(experience_id)
    if not fiche:
        return {"variantes": [], "probleme": "experience introuvable"}
    if not fiche.get("produit_id"):
        return {"variantes": [],
                "probleme": "experience sans produit : impossible de savoir "
                            "quelles ventes lui attribuer"}
    mesures = []
    for variante in variantes(experience_id):
        debut, fin = variante.get("debut"), variante.get("fin")
        if not debut:
            mesures.append({"variante": variante, "ventes": 0, "jours": 0.0,
                            "periode": ""})
            continue
        fin_effective = fin or time.strftime("%Y-%m-%d")
        with store.cursor() as cur:
            ligne = cur.execute(
                "SELECT COALESCE(SUM(CASE WHEN remboursement = 0"
                " THEN unites ELSE 0 END), 0) AS ventes"
                " FROM ventes WHERE produit_id = ? AND date >= ? AND date <= ?",
                (fiche["produit_id"], debut, fin_effective)).fetchone()
        mesures.append({
            "variante": variante, "ventes": int(ligne["ventes"] or 0),
            "jours": _jours(debut, fin_effective),
            "periode": "{} au {}".format(debut, fin_effective),
        })
    return {"variantes": mesures, "probleme": "",
            "produit_id": fiche["produit_id"]}


def _jours(debut: str, fin: str) -> float:
    """Duree d'exposition, bornes comprises : un seul jour compte pour un."""
    format_date = "%Y-%m-%d"
    ecart = (time.mktime(time.strptime(fin, format_date))
             - time.mktime(time.strptime(debut, format_date)))
    return max(1.0, round(ecart / 86400.0) + 1.0)


def variantes(experience_id: int) -> List[Dict[str, Any]]:
    _assurer()
    with store.cursor() as cur:
        cur.execute(
            "SELECT v.*, COALESCE(SUM(o.vues),0) AS total_vues,"
            " COALESCE(SUM(o.actions),0) AS total_actions,"
            " COUNT(o.id) AS releves"
            " FROM variantes v LEFT JOIN observations o ON o.variante_id = v.id"
            " WHERE v.experience_id=? GROUP BY v.id ORDER BY v.id",
            (experience_id,),
        )
        sortie = []
        for ligne in cur.fetchall():
            entree = dict(ligne)
            entree["meta"] = json.loads(entree.get("meta") or "{}")
            sortie.append(entree)
        return sortie


def lire(experience_id: int) -> Optional[Dict[str, Any]]:
    _assurer()
    with store.cursor() as cur:
        cur.execute("SELECT * FROM experiences WHERE id=?", (experience_id,))
        ligne = cur.fetchone()
        return dict(ligne) if ligne else None


def lister(limite: int = 30) -> List[Dict[str, Any]]:
    _assurer()
    with store.cursor() as cur:
        cur.execute(
            "SELECT e.*, COUNT(v.id) AS nb_variantes"
            " FROM experiences e LEFT JOIN variantes v ON v.experience_id = e.id"
            " GROUP BY e.id ORDER BY e.cree_le DESC LIMIT ?", (limite,))
        return [dict(ligne) for ligne in cur.fetchall()]


def analyser(experience_id: int) -> Dict[str, Any]:
    """Etat complet d'une experience : variantes, statistiques, verdict."""
    experience = lire(experience_id)
    if experience is None:
        return {"erreur": "experience inconnue"}
    lot = variantes(experience_id)
    if not lot:
        return {"experience": experience, "variantes": [],
                "verdict": {"etat": "vide", "message": "Aucune variante."}}

    comparaison = comparer([(v["total_actions"], v["total_vues"]) for v in lot])
    for variante, statistique in zip(lot, comparaison["variantes"]):
        variante["stats"] = statistique
    return {
        "experience": experience,
        "variantes": lot,
        "comparaison": comparaison,
        "verdict": verdict(comparaison),
    }


def cloturer(experience_id: int, gagnante_id: int = 0, note: str = "") -> None:
    _assurer()
    with store.cursor() as cur:
        cur.execute(
            "UPDATE experiences SET statut='close', gagnante=?, note=?, maj_le=?"
            " WHERE id=?",
            (gagnante_id or None, note[:300], time.time(), experience_id),
        )


def supprimer(experience_id: int) -> bool:
    _assurer()
    with store.cursor() as cur:
        cur.execute("SELECT id FROM variantes WHERE experience_id=?",
                    (experience_id,))
        identifiants = [ligne["id"] for ligne in cur.fetchall()]
        for identifiant in identifiants:
            cur.execute("DELETE FROM observations WHERE variante_id=?",
                        (identifiant,))
        cur.execute("DELETE FROM variantes WHERE experience_id=?", (experience_id,))
        cur.execute("DELETE FROM experiences WHERE id=?", (experience_id,))
        return cur.rowcount > 0
