"""Les ventes reelles : ce que l'usine ne savait pas de son propre travail.

L'usine mesurait la qualite, la duree, les appels consommes, les defauts
restants. Elle ne savait rien de ce qui rapporte. « usine bilan » pouvait
donc repondre « quel ton donne vos meilleures notes » et jamais « quelle
niche a paye ». Les deux questions n'ont aucune raison d'avoir la meme
reponse, et c'est la seconde qui decide ce qu'on fabrique ensuite.

Trois regles de prudence, parce qu'un chiffre d'affaires invente est pire
qu'un chiffre d'affaires absent :

  PAS DE CONVERSION  les devises ne sont jamais melangees. Convertir sans
                     source de taux reviendrait a fabriquer le resultat.
  PAS D'ESTIMATION   le net est enregistre s'il figure dans l'export,
                     laisse vide sinon. Deduire une commission « habituelle »
                     donnerait un revenu qui n'existe pas.
  PAS DE DOUBLON     chaque ligne importee porte une empreinte ; reimporter
                     le meme export n'ajoute rien.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
import time
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import store

# --------------------------------------------------------------------------
# Lecture d'un export de place de marche
# --------------------------------------------------------------------------

# Les exports changent de colonnes sans prevenir, et d'une place a l'autre.
# Plutot que de coder en dur le format de Gumroad de ce mois-ci, on cherche
# la colonne par ses noms possibles et on DIT ce qu'on a reconnu : une
# correspondance affichee se verifie, une correspondance devinee ne se
# verifie pas.
ALIAS: Dict[str, Tuple[str, ...]] = {
    "date": ("date", "purchase date", "sale date", "order date", "created at",
             "date de vente", "date d achat", "timestamp", "datetime",
             "date paid", "sold on"),
    "reference": ("product", "product name", "item", "item name", "title",
                  "listing title", "produit", "nom du produit", "article",
                  "description", "variant", "item title"),
    "unites": ("quantity", "qty", "units", "quantite", "nombre",
               "number of items", "item quantity"),
    "brut": ("price", "gross", "gross amount", "subtotal", "amount",
             "order total", "item total", "prix", "montant", "total",
             "revenue", "sale price", "price (eur)", "order value"),
    "net": ("net", "net amount", "earnings", "your earnings", "payout",
            "net revenue", "revenu net", "montant net", "seller earnings",
            "item net"),
    "devise": ("currency", "devise", "currency code"),
    "remboursement": ("refunded", "refund", "is refunded", "rembourse",
                      "status", "statut", "state"),
    "identifiant": ("order id", "order number", "sale id", "transaction id",
                    "receipt id", "id", "reference", "numero de commande"),
}

_DATE_ISO = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
_DATE_COURTE = re.compile(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})")


def _plat(texte: str) -> str:
    sans = unicodedata.normalize("NFKD", (texte or "").strip().lower())
    sans = sans.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", " ", sans).strip()


def _nombre(brut: str) -> Optional[float]:
    """Lit un montant, quelle que soit la convention d'ecriture.

    « 1 234,56 € », « $1,234.56 » et « 1234.56 » donnent le meme nombre.
    Distinguer le separateur decimal du separateur de milliers se fait par
    la position : le dernier des deux, s'il ne reste que deux chiffres
    apres lui, est le decimal.
    """
    if brut is None:
        return None
    texte = re.sub(r"[^0-9,.\-]", "", str(brut))
    if not texte or texte in ("-", ".", ","):
        return None
    virgule, point = texte.rfind(","), texte.rfind(".")
    if virgule > point:
        texte = texte.replace(".", "").replace(",", ".")
    else:
        texte = texte.replace(",", "")
    try:
        return float(texte)
    except ValueError:
        return None


def convention_dates(valeurs: Sequence[str]) -> str:
    """Decide si un fichier ecrit ses dates en jour/mois ou en mois/jour.

    La decision se prend sur le FICHIER, pas sur la ligne. « 03/08/2026 »
    est indecidable seul ; « 31/12/2024 » ailleurs dans le meme export
    tranche pour tout le monde, puisqu'une place de marche n'alterne pas
    les conventions au sein d'un export.

    Sans indice, on retient jour/mois : l'usine est ecrite en francais, et
    se tromper dans ce sens donne une date decalee, la ou l'ancienne
    version fabriquait des mois numero 31 — donc des dates qu'aucune
    comparaison ne retrouvait jamais.
    """
    for valeur in valeurs:
        trouve = _DATE_COURTE.search((valeur or "").strip())
        if not trouve:
            continue
        premier, second = int(trouve.group(1)), int(trouve.group(2))
        if premier > 12 and second <= 12:
            return "jma"
        if second > 12 and premier <= 12:
            return "mja"
    return "jma"


def _date(brut: str, convention: str = "jma") -> str:
    """Ramene une date a la forme AAAA-MM-JJ. Renvoie '' si illisible."""
    texte = (brut or "").strip()
    trouve = _DATE_ISO.search(texte)
    if trouve:
        return "{}-{}-{}".format(*trouve.groups())
    trouve = _DATE_COURTE.search(texte)
    if not trouve:
        return ""
    premier, second, annee = (int(trouve.group(1)), int(trouve.group(2)),
                              trouve.group(3))
    if convention == "mja":
        mois, jour = premier, second
    else:
        jour, mois = premier, second
    # Une date impossible vaut mieux refusee que rangee : « 2024-31-12 » se
    # compare comme une chaine et ne ressort d'aucune requete.
    if not (1 <= mois <= 12 and 1 <= jour <= 31):
        return ""
    return "{}-{:02d}-{:02d}".format(annee, mois, jour)


def _dialecte(entete: str) -> str:
    """Virgule ou point-virgule : un tableur francais exporte en point-virgule."""
    return ";" if entete.count(";") > entete.count(",") else ","


def reconnaitre(colonnes: Sequence[str]) -> Dict[str, str]:
    """Associe chaque champ attendu a une colonne du fichier, ou a rien.

    Deux regles, apprises d'un export ou la colonne « Paid » etait prise
    pour l'identifiant de commande — l'alias « id » s'y trouvait en tant que
    SOUS-CHAINE. Toutes les ventes recevaient alors la meme empreinte, et
    l'index unique les jetait toutes sauf une, en annoncant « deja
    connue(s) ».

      1. la correspondance approchee se fait sur des MOTS entiers, pas sur
         des sous-chaines ;
      2. une colonne deja retenue pour un champ n'est plus candidate pour
         un autre.
    """
    plates = {_plat(c): c for c in colonnes}
    correspondance: Dict[str, str] = {}
    prises = set()

    def retenir(champ: str, colonne: str) -> None:
        correspondance[champ] = colonne
        prises.add(colonne)

    # Premier tour : les noms exacts, qui ne se disputent rien.
    for champ, noms in ALIAS.items():
        for nom in noms:
            colonne = plates.get(nom)
            if colonne and colonne not in prises:
                retenir(champ, colonne)
                break

    # Second tour : un alias doit apparaitre comme mot entier dans le nom.
    for champ, noms in ALIAS.items():
        if champ in correspondance:
            continue
        for nom in noms:
            mots_alias = nom.split()
            for plat, brut in plates.items():
                if brut in prises:
                    continue
                mots = plat.split()
                if all(m in mots for m in mots_alias):
                    retenir(champ, brut)
                    break
            if champ in correspondance:
                break
    return correspondance


@dataclass
class Lecture:
    """Ce qu'un fichier d'export a donne, et ce qu'il n'a pas donne."""

    lignes: List[Dict[str, Any]] = field(default_factory=list)
    correspondance: Dict[str, str] = field(default_factory=dict)
    colonnes: List[str] = field(default_factory=list)
    ignorees: int = 0
    manquants: List[str] = field(default_factory=list)
    convention: str = "jma"      # ordre jour/mois retenu pour ce fichier

    @property
    def exploitable(self) -> bool:
        return not self.manquants and bool(self.lignes)


def lire_export(texte: str, plateforme: str = "") -> Lecture:
    """Lit un export CSV sans rien supposer de son format exact."""
    premiere = texte.splitlines()[0] if texte.strip() else ""
    rangs = list(csv.DictReader(io.StringIO(texte),
                                delimiter=_dialecte(premiere)))
    colonnes = [c for c in (csv.DictReader(io.StringIO(texte),
                                           delimiter=_dialecte(premiere))
                            .fieldnames or []) if c]
    correspondance = reconnaitre(colonnes)
    lecture = Lecture(correspondance=correspondance, colonnes=colonnes)
    for champ in ("date", "brut"):
        if champ not in correspondance:
            lecture.manquants.append(champ)
    if lecture.manquants:
        return lecture

    # La convention de date se decide sur l'ensemble du fichier avant de lire
    # la premiere ligne : une seule date sans ambiguite tranche pour toutes.
    lecture.convention = convention_dates(
        [r.get(correspondance["date"], "") for r in rangs])

    for rang in rangs:
        date = _date(rang.get(correspondance["date"], ""), lecture.convention)
        brut = _nombre(rang.get(correspondance["brut"], ""))
        if not date or brut is None:
            lecture.ignorees += 1
            continue
        reference = (rang.get(correspondance.get("reference", ""), "") or "").strip()
        unites = _nombre(rang.get(correspondance.get("unites", ""), "")) or 1
        net = _nombre(rang.get(correspondance.get("net", ""), ""))
        devise = (rang.get(correspondance.get("devise", ""), "") or "EUR").strip()
        colonne_etat = correspondance.get("remboursement", "")
        rembourse = _rembourse(colonne_etat, rang.get(colonne_etat, ""))
        marqueur = rang.get(correspondance.get("identifiant", ""), "") or ""
        lecture.lignes.append({
            "date": date, "reference": reference[:180],
            "unites": max(1, int(unites)), "brut": brut, "net": net,
            "devise": (devise[:8] or "EUR").upper(),
            "remboursement": 1 if rembourse else 0,
            "plateforme": plateforme or "import",
            "empreinte": _empreinte(plateforme, marqueur, date, reference,
                                    brut, rang),
        })
    return lecture


def _rembourse(colonne: str, valeur: str) -> bool:
    """Vrai si la ligne est un remboursement.

    Le nom de la colonne compte autant que son contenu. Une colonne
    « Refunded » vaut par oui ou par non ; une colonne « Statut » decrit un
    etat, et y lire « 1 » comme un remboursement transformerait une vente en
    perte. Les valeurs booleennes ne sont donc acceptees que d'une colonne
    qui annonce un remboursement.
    """
    etat = _plat(valeur)
    if not etat:
        return False
    if "refund" in etat or "rembours" in etat:
        return True
    nom = _plat(colonne)
    if "refund" in nom or "rembours" in nom:
        return etat in ("true", "yes", "oui", "1", "vrai", "y", "o")
    return False


def _empreinte(plateforme: str, marqueur: str, date: str, reference: str,
               brut: float, rang: Dict[str, Any]) -> str:
    """Identifie une ligne pour que la reimporter n'ajoute rien.

    L'identifiant de commande quand la place en fournit un ; sinon
    l'empreinte de la ligne entiere, ce qui suffit tant que deux ventes
    strictement identiques ne se produisent pas le meme jour — auquel cas la
    seconde est perdue, et c'est le compromis retenu contre le risque
    inverse, compter deux fois la meme vente.
    """
    if marqueur.strip():
        graine = "{}|{}".format(plateforme, marqueur.strip())
    else:
        graine = "{}|{}|{}|{}|{}".format(
            plateforme, date, reference, brut,
            "|".join(str(v) for v in sorted(rang.values(), key=str)))
    return hashlib.sha256(graine.encode("utf-8")).hexdigest()[:32]


# --------------------------------------------------------------------------
# Enregistrement
# --------------------------------------------------------------------------

def enregistrer(ligne: Dict[str, Any], produit_id: str = "") -> bool:
    """Ajoute une vente. Renvoie False si elle etait deja connue."""
    with store.cursor() as cur:
        try:
            cur.execute(
                "INSERT INTO ventes (produit_id, reference, plateforme, date,"
                " unites, brut, net, devise, remboursement, source, empreinte,"
                " cree_le) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (produit_id or None, ligne.get("reference", ""),
                 ligne.get("plateforme", "manuel"), ligne["date"],
                 int(ligne.get("unites", 1)), float(ligne.get("brut", 0)),
                 ligne.get("net"), ligne.get("devise", "EUR"),
                 int(ligne.get("remboursement", 0)),
                 ligne.get("source", ligne.get("plateforme", "manuel")),
                 ligne.get("empreinte"), time.time()),
            )
        except Exception as exc:            # UNIQUE sur l'empreinte
            if "UNIQUE" in str(exc):
                return False
            raise
    return True


def lier(reference: str, produit_id: str) -> int:
    """Rattache toutes les ventes portant cette reference a un produit."""
    with store.cursor() as cur:
        cur.execute("UPDATE ventes SET produit_id = ? WHERE reference = ?",
                    (produit_id, reference))
        return cur.rowcount


def rattacher_automatiquement(seuil: float = 0.75) -> List[Tuple[str, str, float]]:
    """Devine a quel produit correspond chaque reference non rattachee.

    Le nom affiche sur la place de marche n'est pas le titre interne : il a
    ete raccourci, traduit, augmente d'un « (PDF + EPUB) ». La comparaison
    reutilise la mesure de proximite des intitules de niche.
    """
    from . import empreinte as emp

    connus = store.lister_produits(500)
    propositions = []
    with store.cursor() as cur:
        references = [r[0] for r in cur.execute(
            "SELECT DISTINCT reference FROM ventes"
            " WHERE produit_id IS NULL AND reference != ''")]
    for reference in references:
        meilleur, score = None, 0.0
        for produit in connus:
            mesure = max(
                emp.ressemblance_reference(reference, produit["titre"] or ""),
                emp.ressemblance_reference(reference, produit["sujet"] or ""))
            if mesure > score:
                meilleur, score = produit, mesure
        if meilleur and score >= seuil:
            propositions.append((reference, meilleur["id"], round(score, 2)))
    return propositions


# --------------------------------------------------------------------------
# Lecture
# --------------------------------------------------------------------------

def total_par_devise(depuis: str = "") -> List[Dict[str, Any]]:
    """Chiffre d'affaires par devise. Jamais converti, jamais additionne."""
    requete = (
        "SELECT devise,"
        " SUM(CASE WHEN remboursement = 0 THEN unites ELSE 0 END) AS unites,"
        " SUM(CASE WHEN remboursement = 0 THEN brut ELSE -brut END) AS brut,"
        " SUM(CASE WHEN remboursement = 0 THEN COALESCE(net, 0)"
        "          ELSE -COALESCE(net, 0) END) AS net,"
        " SUM(CASE WHEN net IS NULL THEN 1 ELSE 0 END) AS net_inconnu,"
        " SUM(remboursement) AS rembourses, COUNT(*) AS lignes"
        " FROM ventes")
    parametres: List[Any] = []
    if depuis:
        requete += " WHERE date >= ?"
        parametres.append(depuis)
    requete += " GROUP BY devise ORDER BY brut DESC"
    with store.cursor() as cur:
        return [dict(r) for r in cur.execute(requete, parametres)]


def par_produit(limite: int = 40) -> List[Dict[str, Any]]:
    with store.cursor() as cur:
        return [dict(r) for r in cur.execute(
            "SELECT v.produit_id, v.devise, p.titre, p.type, p.sujet,"
            " SUM(CASE WHEN v.remboursement = 0 THEN v.unites ELSE 0 END) AS unites,"
            " SUM(CASE WHEN v.remboursement = 0 THEN v.brut ELSE -v.brut END) AS brut,"
            " SUM(v.remboursement) AS rembourses"
            " FROM ventes v LEFT JOIN produits p ON p.id = v.produit_id"
            " WHERE v.produit_id IS NOT NULL"
            " GROUP BY v.produit_id, v.devise"
            " ORDER BY brut DESC LIMIT ?", (int(limite),))]


def par_champ(champ: str, minimum: int = 1) -> List[Dict[str, Any]]:
    """Chiffre d'affaires groupe par une colonne de la table produits."""
    if champ not in ("type", "langue", "audience"):
        raise ValueError("champ non groupable : {}".format(champ))
    with store.cursor() as cur:
        lignes = [dict(r) for r in cur.execute(
            "SELECT p.{champ} AS valeur, v.devise,"
            " COUNT(DISTINCT v.produit_id) AS produits,"
            " SUM(CASE WHEN v.remboursement = 0 THEN v.unites ELSE 0 END) AS unites,"
            " SUM(CASE WHEN v.remboursement = 0 THEN v.brut ELSE -v.brut END) AS brut"
            " FROM ventes v JOIN produits p ON p.id = v.produit_id"
            " GROUP BY p.{champ}, v.devise"
            " ORDER BY brut DESC".format(champ=champ))]
    return [l for l in lignes if (l["produits"] or 0) >= minimum]


def prix_observes(type_produit: str = "") -> List[Dict[str, Any]]:
    """Prix unitaires reellement encaisses, par devise.

    C'est le seul chiffre qui vaille pour conseiller un prix. Celui que
    proposait l'explorateur de niches sortait du modele, sans aucune mesure
    derriere — le nombre qui decide du revenu etait le moins fonde de tout
    le systeme.
    """
    requete = (
        "SELECT v.devise, v.brut / MAX(v.unites, 1) AS unitaire"
        " FROM ventes v LEFT JOIN produits p ON p.id = v.produit_id"
        " WHERE v.remboursement = 0 AND v.brut > 0")
    parametres: List[Any] = []
    if type_produit:
        requete += " AND p.type = ?"
        parametres.append(type_produit)
    with store.cursor() as cur:
        lignes = [dict(r) for r in cur.execute(requete, parametres)]
    par_devise: Dict[str, List[float]] = {}
    for ligne in lignes:
        par_devise.setdefault(ligne["devise"], []).append(ligne["unitaire"])
    resultat = []
    for devise, valeurs in par_devise.items():
        valeurs.sort()
        resultat.append({
            "devise": devise, "ventes": len(valeurs),
            "median": _mediane(valeurs),
            "bas": valeurs[int(len(valeurs) * 0.25)],
            "haut": valeurs[min(len(valeurs) - 1, int(len(valeurs) * 0.75))],
        })
    resultat.sort(key=lambda r: r["ventes"], reverse=True)
    return resultat


def _mediane(valeurs: Sequence[float]) -> float:
    if not valeurs:
        return 0.0
    milieu = len(valeurs) // 2
    if len(valeurs) % 2:
        return valeurs[milieu]
    return (valeurs[milieu - 1] + valeurs[milieu]) / 2.0


def resume_pour_ia(limite: int = 8) -> str:
    """Ce que les ventes disent, a injecter dans l'exploration de niches."""
    produits = par_produit(limite)
    if not produits:
        return ""
    lignes = ["Ventes reellement constatees par ce vendeur :"]
    for produit in produits:
        lignes.append("- {} ({}) : {} unites, {:.0f} {}".format(
            (produit["titre"] or produit["produit_id"])[:52],
            produit["type"] or "?", produit["unites"] or 0,
            produit["brut"] or 0, produit["devise"]))
    types = par_champ("type")
    if types:
        lignes.append("Par type : " + ", ".join(
            "{} = {:.0f} {}".format(t["valeur"], t["brut"] or 0, t["devise"])
            for t in types[:5]))
    return "\n".join(lignes)
