"""Reconnaissance et audit de surface d'un domaine, pour la divulgation
responsable.

Ce module fait UNE chose et refuse d'en faire une autre.

Ce qu'il fait — de la reconnaissance PASSIVE et un audit de SURFACE :
lire des registres publics (journaux de transparence des certificats, DNS,
RDAP) et, sur autorisation, lire la posture qu'un site publie lui-meme
(ses en-tetes de reponse, son security.txt, son certificat). C'est ce que
fait un navigateur en ouvrant une page. Ca trouve de vraies failles a
signaler : e-mail usurpable faute de DMARC, en-tetes de securite absents,
depot .git expose, TLS faible, pas de point de contact securite.

Ce qu'il NE fait PAS, et ne fera pas : envoyer une charge d'attaque
(injection, XSS, commande), forcer un mot de passe, balayer des ports en
masse, exploiter quoi que ce soit, ou contourner une protection. Ce n'est
pas de la prudence : scanner ainsi un bien d'autrui est illegal sans son
accord ecrit, quelle que soit l'intention, et l'outil ferait tomber celui
qui s'en sert.

Deux niveaux, et la difference est la ligne legale :

- PASSIF (par defaut, aucune autorisation requise) : crt.sh, DNS-sur-HTTPS,
  RDAP. Zero paquet vers la cible. « Presque universellement permis »
  parce qu'on ne lit que des donnees publiques.
- SURFACE (exige une autorisation affirmee) : une requete HTTPS vers la
  cible pour lire ses propres en-tetes, son security.txt, son certificat.
  Une seule, benigne. On la place derriere une porte parce qu'elle TOUCHE
  la cible, et parce qu'affirmer le perimetre est la bonne habitude.
"""

from __future__ import annotations

import json
import re
import socket
import ssl
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from .http import HttpErreur, requete, requete_complete

# Resolveurs DNS-sur-HTTPS : la bibliotheque standard n'a pas de resolveur
# capable de lire un enregistrement TXT ou MX. On passe donc par l'API JSON
# de resolveurs publics — toujours en lisant, jamais en interrogeant la cible.
DOH = "https://dns.google/resolve?name={nom}&type={type}"
CT = "https://crt.sh/?q=%25.{domaine}&output=json"
RDAP = "https://rdap.org/domain/{domaine}"

# Les en-tetes de securite qu'un site sert (ou pas), et ce que leur absence
# ouvre. C'est la moitie la plus utile d'un rapport de divulgation.
ENTETES_SECURITE = {
    "strict-transport-security": (
        "grave", "HSTS absent : une premiere visite en http peut etre "
        "detournee (SSL stripping)."),
    "content-security-policy": (
        "moyen", "CSP absente : rien ne limite les scripts charges, "
        "premiere ligne contre le XSS."),
    "x-content-type-options": (
        "faible", "X-Content-Type-Options absent : le navigateur peut "
        "deviner un type MIME et executer un fichier innocent."),
    "x-frame-options": (
        "faible", "X-Frame-Options / frame-ancestors absent : la page peut "
        "etre encadree ailleurs (clickjacking)."),
    "referrer-policy": (
        "info", "Referrer-Policy absent : l'URL complete fuit vers les "
        "sites tiers."),
}


@dataclass
class Constat:
    """Un fait a signaler, avec sa gravite et son explication."""

    gravite: str          # grave | moyen | faible | info | ok
    domaine: str          # dns | courriel | entetes | tls | exposition | contact
    titre: str
    detail: str = ""

    def dict(self) -> Dict[str, str]:
        return {"gravite": self.gravite, "domaine": self.domaine,
                "titre": self.titre, "detail": self.detail}


@dataclass
class Rapport:
    """Ce qu'une reconnaissance a rassemble sur un domaine."""

    cible: str
    passif_seul: bool = True
    sous_domaines: List[str] = field(default_factory=list)
    enregistrements: Dict[str, List[str]] = field(default_factory=dict)
    contact: str = ""           # point de contact securite trouve
    constats: List[Constat] = field(default_factory=list)
    erreurs: List[str] = field(default_factory=list)

    @property
    def score(self) -> int:
        """Note de posture sur 100, calculee sur ce qu'on a pu voir.

        Volontairement grossiere : elle ordonne, elle ne juge pas. Un site
        qu'on n'a pas pu auditer en surface part avec un score prudent.
        """
        poids = {"grave": 25, "moyen": 12, "faible": 5, "info": 1}
        perdu = sum(poids.get(c.gravite, 0) for c in self.constats)
        return max(0, 100 - perdu)

    def par_gravite(self, gravite: str) -> List[Constat]:
        return [c for c in self.constats if c.gravite == gravite]

    def dict(self) -> Dict[str, Any]:
        return {
            "cible": self.cible,
            "passif_seul": self.passif_seul,
            "score": self.score,
            "sous_domaines": self.sous_domaines,
            "enregistrements": self.enregistrements,
            "contact": self.contact,
            "constats": [c.dict() for c in self.constats],
            "erreurs": self.erreurs,
        }


# --------------------------------------------------------------------------
# Normalisation
# --------------------------------------------------------------------------

def normaliser_domaine(brut: str) -> str:
    """Extrait un nom de domaine nu d'une saisie libre (URL, espaces, port)."""
    texte = (brut or "").strip().lower()
    texte = re.sub(r"^[a-z]+://", "", texte)      # schema
    texte = texte.split("/")[0].split("?")[0]      # chemin, requete
    texte = texte.split(":")[0]                    # port
    texte = texte.strip(".")
    if texte.startswith("www."):
        texte = texte[4:]
    return texte


def _valide(domaine: str) -> bool:
    return bool(re.match(
        r"^(?=.{1,253}$)([a-z0-9](-?[a-z0-9])*\.)+[a-z]{2,}$", domaine))


# --------------------------------------------------------------------------
# Reconnaissance passive : que des donnees publiques, zero paquet vers la cible
# --------------------------------------------------------------------------

def _doh(nom: str, type_: str) -> Tuple[List[str], bool]:
    """Un enregistrement DNS via DNS-sur-HTTPS. Renvoie (valeurs, AD).

    AD = « Authenticated Data » : le resolveur a valide DNSSEC. C'est ainsi
    qu'on sait, sans creuser, si le domaine est signe.
    """
    try:
        statut, brut = requete(DOH.format(nom=nom, type=type_), timeout=12)
    except HttpErreur:
        return [], False
    if statut != 200:
        return [], False
    try:
        donnees = json.loads(brut.decode("utf-8", "replace"))
    except ValueError:
        return [], False
    valeurs = [r.get("data", "").strip('"') for r in donnees.get("Answer", [])]
    return [v for v in valeurs if v], bool(donnees.get("AD"))


def sous_domaines(domaine: str, limite: int = 60) -> Tuple[List[str], str]:
    """Sous-domaines vus dans les journaux de transparence des certificats.

    Chaque certificat HTTPS demande est publiquement journalise (c'est le
    principe de la Certificate Transparency). On y lit la surface d'un
    domaine — sous-domaines internes compris — sans jamais le contacter.
    """
    try:
        statut, brut = requete(CT.format(domaine=domaine), timeout=25)
    except HttpErreur as exc:
        return [], "crt.sh injoignable ({})".format(exc)
    if statut != 200:
        return [], "crt.sh a repondu {}".format(statut)
    try:
        lignes = json.loads(brut.decode("utf-8", "replace"))
    except ValueError:
        return [], "reponse crt.sh illisible"
    noms = set()
    for ligne in lignes:
        for nom in str(ligne.get("name_value", "")).splitlines():
            nom = nom.strip().lower().lstrip("*.")
            if nom.endswith(domaine) and _valide(nom):
                noms.add(nom)
    return sorted(noms)[:limite], ""


def courriel(domaine: str) -> List[Constat]:
    """Posture anti-usurpation de l'e-mail : SPF, DMARC, DNSSEC.

    C'est le constat qui rapporte le plus dans une divulgation : un domaine
    sans DMARC laisse n'importe qui envoyer des e-mails en son nom.
    """
    constats: List[Constat] = []
    txt, ad = _doh(domaine, "TXT")
    spf = [t for t in txt if t.lower().startswith("v=spf1")]
    if not spf:
        constats.append(Constat(
            "moyen", "courriel", "Aucun enregistrement SPF",
            "Rien ne declare quels serveurs peuvent envoyer pour ce domaine."))
    elif any("+all" in t or " all" in t.replace("~", " ").replace("-", " ")
             for t in spf):
        constats.append(Constat(
            "moyen", "courriel", "SPF trop permissif",
            "Un « +all » ou « ?all » autorise tout le monde a envoyer."))

    dmarc, _ = _doh("_dmarc." + domaine, "TXT")
    politique = ""
    for t in dmarc:
        trouve = re.search(r"p=(\w+)", t)
        if t.lower().startswith("v=dmarc1") and trouve:
            politique = trouve.group(1).lower()
    if not politique:
        constats.append(Constat(
            "grave", "courriel", "Aucun DMARC",
            "L'e-mail du domaine est usurpable : n'importe qui peut ecrire "
            "en son nom. C'est la faille la plus courante et la plus facile "
            "a signaler."))
    elif politique == "none":
        constats.append(Constat(
            "moyen", "courriel", "DMARC en observation seule (p=none)",
            "La politique existe mais ne rejette rien : l'usurpation passe."))
    else:
        constats.append(Constat(
            "ok", "courriel", "DMARC actif (p={})".format(politique)))

    if not ad:
        constats.append(Constat(
            "info", "dns", "DNSSEC non valide ou absent",
            "Les reponses DNS ne sont pas signees : empoisonnement plus facile."))
    return constats


def rdap(domaine: str) -> Dict[str, Any]:
    """Enregistrement RDAP (le WHOIS moderne, en JSON). Purement public."""
    try:
        statut, brut = requete(RDAP.format(domaine=domaine), timeout=15)
    except HttpErreur:
        return {}
    if statut != 200:
        return {}
    try:
        donnees = json.loads(brut.decode("utf-8", "replace"))
    except ValueError:
        return {}
    evenements = {e.get("eventAction"): e.get("eventDate")
                  for e in donnees.get("events", [])}
    return {
        "registrar": next((e.get("vcardArray", [None, []])[1]
                           for e in donnees.get("entities", [])
                           if "registrar" in e.get("roles", [])), None) and "",
        "cree": evenements.get("registration", ""),
        "expire": evenements.get("expiration", ""),
        "statuts": donnees.get("status", []),
    }


# --------------------------------------------------------------------------
# Audit de surface : UNE requete vers la cible, sur autorisation
# --------------------------------------------------------------------------

def _certificat(domaine: str, timeout: int = 10) -> Tuple[Dict[str, Any], str]:
    """Lit le certificat TLS presente par le domaine. Une poignee de main."""
    contexte = ssl.create_default_context()
    try:
        with socket.create_connection((domaine, 443), timeout=timeout) as brut:
            with contexte.wrap_socket(brut, server_hostname=domaine) as tls:
                cert = tls.getpeercert()
                version = tls.version()
    except (OSError, ssl.SSLError) as exc:
        return {}, str(exc)
    return {"expire": cert.get("notAfter", ""),
            "emetteur": dict(x[0] for x in cert.get("issuer", [])).get(
                "organizationName", ""),
            "version_tls": version}, ""


def surface(domaine: str) -> List[Constat]:
    """Lit la posture qu'un site publie lui-meme. UNE requete HTTPS.

    Rien ici n'attaque : on lit les en-tetes de reponse, le certificat, et
    deux fichiers FAITS pour etre lus (security.txt, robots.txt). La seule
    verification limite est celle du depot .git expose — un fichier qui ne
    devrait jamais etre public, qu'on lit sans l'exploiter.
    """
    constats: List[Constat] = []
    base = "https://" + domaine

    try:
        statut, entetes, _ = requete_complete(base, timeout=15)
    except HttpErreur as exc:
        return [Constat("info", "entetes", "Site injoignable en HTTPS",
                        str(exc))]

    for cle, (gravite, message) in ENTETES_SECURITE.items():
        present = cle in entetes
        if cle == "x-frame-options" and "content-security-policy" in entetes:
            if "frame-ancestors" in entetes["content-security-policy"].lower():
                present = True
        if not present:
            constats.append(Constat(gravite, "entetes",
                                    "En-tete manquant : " + cle, message))

    banniere = entetes.get("server", "")
    if banniere and re.search(r"\d", banniere):
        constats.append(Constat(
            "faible", "entetes", "Version du serveur exposee",
            "En-tete « Server: {} » : donne une version a un attaquant.".format(
                banniere)))

    cookies = entetes.get("set-cookie", "")
    if cookies and "secure" not in cookies.lower():
        constats.append(Constat(
            "moyen", "entetes", "Cookie sans attribut Secure",
            "Un cookie de session peut partir en clair."))

    cert, souci = _certificat(domaine)
    if souci:
        constats.append(Constat("moyen", "tls", "TLS problematique", souci))
    elif cert:
        vieux = cert["version_tls"] in ("TLSv1", "TLSv1.1", "SSLv3")
        constats.append(Constat(
            "moyen" if vieux else "ok", "tls",
            "TLS : {}".format(cert["version_tls"]),
            "Version obsolete." if vieux else "Certificat par {}.".format(
                cert.get("emetteur", "?"))))

    # Depot .git expose : un seul GET d'un chemin precis, lu et non exploite.
    try:
        code, _, corps = requete_complete(base + "/.git/HEAD", timeout=10)
        if code == 200 and corps[:5] == b"ref: ":
            constats.append(Constat(
                "grave", "exposition", "Depot .git accessible",
                "/.git/HEAD est servi : le code source et son historique "
                "peuvent etre reconstitues. A signaler en priorite."))
    except HttpErreur:
        pass
    return constats


def contact_securite(domaine: str) -> Tuple[str, List[Constat]]:
    """Cherche le point de contact de divulgation (RFC 9116 security.txt)."""
    for chemin in ("/.well-known/security.txt", "/security.txt"):
        try:
            code, _, corps = requete_complete("https://" + domaine + chemin,
                                              timeout=10)
        except HttpErreur:
            continue
        if code == 200 and b"contact" in corps.lower():
            texte = corps.decode("utf-8", "replace")
            trouve = re.search(r"(?im)^contact:\s*(.+)$", texte)
            contact = trouve.group(1).strip() if trouve else ""
            return contact, [Constat("ok", "contact",
                                     "security.txt present", contact)]
    return "", [Constat(
        "faible", "contact", "Aucun security.txt",
        "Rien n'indique comment signaler une faille : la premiere chose a "
        "recommander au proprietaire (RFC 9116).")]


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------

def auditer(cible: str, autorise: bool = False) -> Rapport:
    """Reconnaissance complete. « autorise » ouvre l'audit de surface.

    Sans autorisation, on reste PASSIF : registres publics uniquement, aucun
    paquet vers la cible. C'est la difference entre lire un annuaire et
    frapper a la porte.
    """
    domaine = normaliser_domaine(cible)
    rapport = Rapport(cible=domaine, passif_seul=not autorise)
    if not _valide(domaine):
        rapport.erreurs.append("« {} » n'est pas un domaine valide.".format(cible))
        return rapport

    # -- passif : toujours --------------------------------------------------
    subs, souci = sous_domaines(domaine)
    rapport.sous_domaines = subs
    if souci:
        rapport.erreurs.append(souci)
    if len(subs) > 25:
        rapport.constats.append(Constat(
            "info", "dns", "{} sous-domaines exposes".format(len(subs)),
            "Grande surface d'attaque visible dans les journaux de "
            "certificats — a passer en revue avec le proprietaire."))

    a, _ = _doh(domaine, "A")
    mx, _ = _doh(domaine, "MX")
    rapport.enregistrements = {"A": a, "MX": mx}
    rapport.constats.extend(courriel(domaine))

    # -- surface : sur autorisation seulement ------------------------------
    if autorise:
        contact, constats_contact = contact_securite(domaine)
        rapport.contact = contact
        rapport.constats.extend(constats_contact)
        rapport.constats.extend(surface(domaine))
    else:
        rapport.constats.append(Constat(
            "info", "contact", "Surface non auditee",
            "Autorisation non confirmee : en-tetes, TLS et exposition non "
            "verifies. Relancez avec l'autorisation pour un site dont vous "
            "avez la charge ou qui figure dans un programme de bug bounty."))

    ordre = {"grave": 0, "moyen": 1, "faible": 2, "ok": 3, "info": 4}
    rapport.constats.sort(key=lambda c: ordre.get(c.gravite, 5))
    return rapport


def rapport_divulgation(rapport: Rapport, chercheur: str = "") -> str:
    """Rediger un signalement pret a envoyer, a partir des constats.

    Divulgation responsable : on decrit ce qui est observable et comment le
    corriger, jamais comment l'exploiter. Le ton reste factuel et courtois —
    on rend service, on ne menace pas.
    """
    signalables = [c for c in rapport.constats
                   if c.gravite in ("grave", "moyen", "faible")]
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    destinataire = rapport.contact or "l'equipe securite (contact introuvable)"

    lignes = [
        "Objet : Signalement de securite — {}".format(rapport.cible),
        "Date : {}".format(date),
        "A : {}".format(destinataire),
        "",
        "Bonjour,",
        "",
        "Je vous ecris dans une demarche de divulgation responsable. En "
        "consultant des informations publiques{} sur {}, j'ai releve les "
        "points suivants, susceptibles d'ameliorer votre securite. Aucune "
        "donnee n'a ete consultee ni aucun systeme sollicite au-dela de ce "
        "qu'un navigateur voit.".format(
            "" if rapport.passif_seul else " et la posture publiee",
            rapport.cible),
        "",
    ]
    if not signalables:
        lignes.append("Bonne nouvelle : rien de notable n'est ressorti. Votre "
                      "posture publique est saine.")
    else:
        for niveau, etiquette in (("grave", "Prioritaire"),
                                  ("moyen", "Important"),
                                  ("faible", "Mineur")):
            lot = [c for c in signalables if c.gravite == niveau]
            if not lot:
                continue
            lignes.append("== {} ==".format(etiquette))
            for c in lot:
                lignes.append("- {} : {}".format(c.titre, c.detail))
            lignes.append("")
    lignes += [
        "Je reste a votre disposition pour tout complement, et je ne "
        "divulguerai rien publiquement sans votre accord et un delai "
        "raisonnable.",
        "",
        "Cordialement,",
        chercheur or "Un chercheur en securite",
    ]
    return "\n".join(lignes)
