"""Controle de conformite d'un EPUB, sans EPUBCheck et sans Java.

EPUBCheck est l'outil de reference, et il ne tournera jamais ici : c'est un
programme Java, et l'usine tient en bibliotheque standard Python sur un
telephone. Plutot que de promettre une validation qu'on ne peut pas faire,
ce module refait en Python les controles STRUCTURELS qu'EPUBCheck applique —
ceux qui rejettent un fichier a la mise en vente :

  - le « mimetype » en premiere entree de l'archive, non compresse. C'est la
    regle la plus mecanique du format, et celle qui casse le plus souvent :
    un ZIP reconstruit a la main la perd, et la liseuse ne reconnait plus le
    fichier comme un livre ;
  - « META-INF/container.xml » qui designe un fichier OPF present ;
  - un OPF bien forme, avec identifiant, titre, langue et date de
    modification — les quatre metadonnees qu'une chaine de distribution lit
    avant tout le reste ;
  - chaque fichier du manifeste present dans l'archive, chaque « itemref »
    du dos pointant vers un identifiant du manifeste, et reciproquement
    aucun fichier orphelin ;
  - un document de navigation declare (« properties="nav" ») et porteur de
    « epub:type="toc" » : c'est lui qui engendre la table des matieres ;
  - du XML bien forme dans chaque XHTML — une balise non fermee passe
    inapercue a l'ecriture et casse la page a la lecture.

Ce que ce module NE fait PAS, et qu'il ne faut pas lui preter : la
validation des schemas XSD, du vocabulaire complet des proprietes, ni la
verification des liens internes entre chapitres. Un fichier « conforme »
ici reste a passer a EPUBCheck avant un depot chez un gros distributeur.
Le rapport le dit lui-meme, plutot que de laisser croire le contraire.
"""

from __future__ import annotations

import posixpath
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set

OPF = "{http://www.idpf.org/2007/opf}"
DC = "{http://purl.org/dc/elements/1.1/}"
CONTENEUR = "{urn:oasis:names:tc:opendocument:xmlns:container}"
XHTML = "{http://www.w3.org/1999/xhtml}"
EPUB_OPS = "{http://www.idpf.org/2007/ops}"

# Fichiers qui n'ont pas a figurer au manifeste.
HORS_MANIFESTE = {"mimetype", "META-INF/container.xml"}


@dataclass
class Rapport:
    """Ce que le controle a trouve. « conforme » ne vaut que pour ces regles."""

    fichier: str = ""
    erreurs: List[str] = field(default_factory=list)
    avertissements: List[str] = field(default_factory=list)
    controles: int = 0

    @property
    def conforme(self) -> bool:
        return not self.erreurs

    def resume(self) -> str:
        if self.erreurs:
            return "{} erreur(s) de structure : {}".format(
                len(self.erreurs), " ; ".join(self.erreurs[:3]))
        if self.avertissements:
            return "structure valide, {} avertissement(s)".format(
                len(self.avertissements))
        return "structure valide ({} controles)".format(self.controles)

    def en_donnees(self) -> Dict[str, object]:
        return {"conforme": self.conforme, "erreurs": self.erreurs,
                "avertissements": self.avertissements,
                "controles": self.controles, "resume": self.resume()}


def verifier_epub(chemin: Path) -> Rapport:
    """Controle structurel d'un EPUB deja ecrit."""
    rapport = Rapport(fichier=Path(chemin).name)
    if not Path(chemin).exists():
        rapport.erreurs.append("fichier absent")
        return rapport
    try:
        with zipfile.ZipFile(chemin) as archive:
            _verifier_archive(archive, rapport)
    except zipfile.BadZipFile:
        rapport.erreurs.append("archive illisible (ZIP invalide)")
    return rapport


def _verifier_archive(archive: zipfile.ZipFile, rapport: Rapport) -> None:
    _verifier_mimetype(archive, rapport)
    racine = _verifier_conteneur(archive, rapport)
    if racine is None:
        return
    _verifier_opf(archive, racine, rapport)


def _verifier_mimetype(archive: zipfile.ZipFile, rapport: Rapport) -> None:
    """La regle la plus mecanique du format, et la plus souvent perdue."""
    entrees = archive.infolist()
    rapport.controles += 3
    if not entrees or entrees[0].filename != "mimetype":
        rapport.erreurs.append(
            "« mimetype » doit etre la premiere entree de l'archive")
        return
    if entrees[0].compress_type != zipfile.ZIP_STORED:
        rapport.erreurs.append("« mimetype » doit rester non compresse")
    if archive.read("mimetype") != b"application/epub+zip":
        rapport.erreurs.append(
            "« mimetype » doit contenir exactement « application/epub+zip »")


def _verifier_conteneur(archive: zipfile.ZipFile,
                        rapport: Rapport) -> Optional[str]:
    """Renvoie le chemin de l'OPF designe, ou None si le conteneur est casse."""
    rapport.controles += 2
    try:
        brut = archive.read("META-INF/container.xml")
    except KeyError:
        rapport.erreurs.append("« META-INF/container.xml » absent")
        return None
    try:
        racine = ET.fromstring(brut)
    except ET.ParseError as exc:
        rapport.erreurs.append("« container.xml » mal forme : {}".format(exc))
        return None
    noeud = racine.find(".//{}rootfile".format(CONTENEUR))
    chemin = noeud.get("full-path", "") if noeud is not None else ""
    if not chemin:
        rapport.erreurs.append("« container.xml » ne designe aucun fichier OPF")
        return None
    if chemin not in archive.namelist():
        rapport.erreurs.append(
            "le fichier OPF annonce est absent de l'archive : {}".format(chemin))
        return None
    return chemin


def _verifier_opf(archive: zipfile.ZipFile, chemin_opf: str,
                  rapport: Rapport) -> None:
    try:
        paquet = ET.fromstring(archive.read(chemin_opf))
    except ET.ParseError as exc:
        rapport.erreurs.append("OPF mal forme : {}".format(exc))
        return

    _verifier_metadonnees(paquet, rapport)
    references = _verifier_manifeste(archive, paquet, chemin_opf, rapport)
    _verifier_dos(paquet, rapport)
    _verifier_navigation(archive, paquet, chemin_opf, rapport)
    _verifier_orphelins(archive, references, rapport)
    _verifier_xhtml(archive, references, rapport)


def _verifier_metadonnees(paquet: ET.Element, rapport: Rapport) -> None:
    """Les quatre metadonnees qu'une chaine de distribution lit en premier."""
    rapport.controles += 4
    identifiant_attendu = paquet.get("unique-identifier", "")
    identifiants = paquet.findall(".//{}identifier".format(DC))
    if not identifiants:
        rapport.erreurs.append("aucun « dc:identifier »")
    elif identifiant_attendu and not any(
            n.get("id") == identifiant_attendu for n in identifiants):
        rapport.erreurs.append(
            "« unique-identifier » ne designe aucun « dc:identifier »")
    for nom in ("title", "language"):
        if paquet.find(".//{}{}".format(DC, nom)) is None:
            rapport.erreurs.append("aucun « dc:{} »".format(nom))
    modifie = [n for n in paquet.findall(".//{}meta".format(OPF))
               if n.get("property") == "dcterms:modified"]
    if not modifie:
        rapport.erreurs.append("aucune date « dcterms:modified »")


def _verifier_manifeste(archive: zipfile.ZipFile, paquet: ET.Element,
                        chemin_opf: str, rapport: Rapport) -> Dict[str, str]:
    """Renvoie {identifiant : chemin dans l'archive} des fichiers declares."""
    base = posixpath.dirname(chemin_opf)
    presents = set(archive.namelist())
    references: Dict[str, str] = {}
    for item in paquet.findall(".//{}item".format(OPF)):
        identifiant, href = item.get("id", ""), item.get("href", "")
        if not identifiant or not href:
            rapport.erreurs.append("entree de manifeste sans « id » ou « href »")
            continue
        if "://" in href:
            continue  # ressource distante : hors de l'archive par nature
        chemin = posixpath.normpath(posixpath.join(base, href))
        rapport.controles += 1
        if chemin not in presents:
            rapport.erreurs.append(
                "declare au manifeste mais absent de l'archive : {}".format(href))
            continue
        references[identifiant] = chemin
    if not references:
        rapport.erreurs.append("manifeste vide")
    return references


def _verifier_dos(paquet: ET.Element, rapport: Rapport) -> None:
    """Le dos (« spine ») donne l'ordre de lecture : il ne doit rien manquer."""
    identifiants = {item.get("id", "")
                    for item in paquet.findall(".//{}item".format(OPF))}
    renvois = paquet.findall(".//{}itemref".format(OPF))
    rapport.controles += 1
    if not renvois:
        rapport.erreurs.append("dos vide : aucun ordre de lecture")
    for renvoi in renvois:
        cible = renvoi.get("idref", "")
        rapport.controles += 1
        if cible not in identifiants:
            rapport.erreurs.append(
                "le dos renvoie a « {} », absent du manifeste".format(cible))


def _verifier_navigation(archive: zipfile.ZipFile, paquet: ET.Element,
                         chemin_opf: str, rapport: Rapport) -> None:
    """Sans document de navigation, pas de table des matieres."""
    rapport.controles += 2
    base = posixpath.dirname(chemin_opf)
    navs = [item for item in paquet.findall(".//{}item".format(OPF))
            if "nav" in (item.get("properties") or "").split()]
    if not navs:
        rapport.erreurs.append(
            "aucun document de navigation (« properties=\"nav\" »)")
        return
    if len(navs) > 1:
        rapport.erreurs.append("plusieurs documents de navigation declares")
    chemin = posixpath.normpath(posixpath.join(base, navs[0].get("href", "")))
    try:
        brut = archive.read(chemin)
    except KeyError:
        return  # deja signale par le controle du manifeste
    try:
        racine = ET.fromstring(brut)
    except ET.ParseError:
        return  # deja signale par le controle des XHTML
    toc = [n for n in racine.iter("{}nav".format(XHTML))
           if n.get("{}type".format(EPUB_OPS)) == "toc"]
    if not toc:
        rapport.erreurs.append(
            "le document de navigation ne porte pas « epub:type=\"toc\" »")
    elif not list(toc[0].iter("{}a".format(XHTML))):
        rapport.erreurs.append("la table des matieres ne contient aucun lien")


def _verifier_orphelins(archive: zipfile.ZipFile, references: Dict[str, str],
                        rapport: Rapport) -> None:
    """Un fichier embarque mais non declare gonfle l'archive pour rien."""
    declares: Set[str] = set(references.values())
    for nom in archive.namelist():
        if nom.endswith("/") or nom in HORS_MANIFESTE or nom in declares:
            continue
        if nom.endswith(".opf"):
            continue  # l'OPF se declare rarement lui-meme
        rapport.controles += 1
        rapport.avertissements.append(
            "present dans l'archive mais absent du manifeste : {}".format(nom))


def _verifier_xhtml(archive: zipfile.ZipFile, references: Dict[str, str],
                    rapport: Rapport) -> None:
    """Une balise non fermee passe inapercue a l'ecriture, pas a la lecture."""
    for chemin in sorted(set(references.values())):
        if not chemin.endswith((".xhtml", ".html", ".ncx", ".opf")):
            continue
        rapport.controles += 1
        try:
            ET.fromstring(archive.read(chemin))
        except ET.ParseError as exc:
            rapport.erreurs.append("{} : XML mal forme ({})".format(
                posixpath.basename(chemin), exc))
