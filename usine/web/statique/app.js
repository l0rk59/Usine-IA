/* Pilotage du tableau de bord : etat, flux temps reel, animation 3D. */
'use strict';

const $ = (id) => document.getElementById(id);
const scene = new SceneUsine($('toile'));
if (!scene.actif) $('scene').classList.add('sans-3d');

const etat = {
  types: [],
  travail: null, agents: {}, fournisseurs: [], avancement: 0, objectif: 0,
  dernierEvenement: 0, produitsCharges: null,
};

/* ------------------------------------------------------------ utilitaires */
function remplirListe(select, valeurs, defaut) {
  select.innerHTML = valeurs
    .map((v) => {
      const [valeur, libelle] = Array.isArray(v) ? v : [v, v];
      const choisi = valeur === defaut ? ' selected' : '';
      return `<option value="${valeur}"${choisi}>${libelle}</option>`;
    })
    .join('');
}

function echapper(texte) {
  return String(texte ?? '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}

function heure(ts) {
  return new Date(ts * 1000).toLocaleTimeString('fr-FR', { hour12: false });
}

/* Compteur qui s'anime au lieu de sauter d'un coup. */
function animerVers(element, cible) {
  const depart = parseInt(element.textContent, 10) || 0;
  if (depart === cible) return;
  const debut = performance.now();
  const duree = 420;
  const pas = (t) => {
    const avance = Math.min(1, (t - debut) / duree);
    const adouci = 1 - Math.pow(1 - avance, 3);
    element.textContent = Math.round(depart + (cible - depart) * adouci);
    if (avance < 1) requestAnimationFrame(pas);
  };
  requestAnimationFrame(pas);
}

function ajouterLigne(html, classe) {
  const journal = $('journal');
  const vide = journal.querySelector('.vide');
  if (vide) vide.remove();
  const ligne = document.createElement('span');
  ligne.className = 'ligne' + (classe ? ' ' + classe : '');
  ligne.innerHTML = html;
  journal.appendChild(ligne);
  while (journal.children.length > 260) journal.removeChild(journal.firstChild);
  journal.scrollTop = journal.scrollHeight;
}

/* --------------------------------------------------------------- chargement */
async function chargerEtat() {
  const reponse = await fetch('/api/etat');
  if (!reponse.ok) return;
  const donnees = await reponse.json();
  $('version').textContent = 'v' + donnees.version;

  etat.fournisseurs = donnees.fournisseurs.map((f) => f.nom);
  scene.majEtat({ fournisseurs: etat.fournisseurs });

  $('jauges').innerHTML = donnees.fournisseurs.map((f) => {
    const part = f.rpd ? Math.min(100, (f.aujourdhui / f.rpd) * 100) : 0;
    const chaud = part > 75 ? ' chaud' : '';
    const etiquette = f.local ? 'local'
      : (f.disponible ? `${f.aujourdhui}/${f.rpd}` : 'sans cle');
    const cles = f.nb_cles > 1 ? ` &times;${f.nb_cles}` : '';
    return `<div class="jauge${f.disponible ? '' : ' absent'}">
      <span class="nom">${echapper(f.nom)}${cles}</span>
      <span class="piste"><span class="remplissage${chaud}"
        style="width:${f.disponible && !f.local ? part : 0}%"></span></span>
      <span class="valeur">${etiquette}</span></div>`;
  }).join('');

  $('conseil').textContent = donnees.avec_cle > 0
    ? `${donnees.avec_cle} fournisseur(s) avec cle — rotation automatique active.`
    : "Aucune cle API : quota tres limite. Lancez « usine cles » dans Termux.";

  if (!$('ton').options.length) {
    etat.types = donnees.types;
    remplirListe($('type'), donnees.types.map((t) => [t.cle, t.nom]), 'ebook');
    decrireType();
    remplirListe($('ton'), donnees.tons, donnees.reglages.ton);
    remplirListe($('taille'), donnees.tailles, donnees.reglages.taille);
    // Les listes sont des raccourcis, pas des limites : la derniere entree
    // ouvre la saisie libre.
    ajouterSurMesure($('ton'), 'autre...');
    ajouterSurMesure($('taille'), 'sur mesure...');
    preselectionner($('ton'), $('ton-libre'), donnees.reglages.ton);
    preselectionner($('taille'), $('chapitres'), donnees.reglages.taille);
    $('ton').addEventListener('change', basculerSurMesure);
    $('taille').addEventListener('change', basculerSurMesure);
    basculerSurMesure();
    remplirListe($('qualite'), donnees.qualites, donnees.reglages.qualite);
    remplirListe($('reseau'), donnees.reseaux, 'linkedin');
    $('auteur').value = donnees.reglages.auteur || '';
    $('audience').value = donnees.reglages.audience || '';
    $('agents').innerHTML = donnees.agents.map((a) =>
      `<span class="agent" data-agent="${a.nom}">
         <span class="pastille"></span>${echapper(a.nom)}</span>`).join('');
  }
}

function preselectionner(liste, champLibre, valeur) {
  // Un reglage sur mesure — un ton ecrit a la main, un nombre de sections —
  // n'est dans aucune liste. Sans ce rattrapage, le navigateur retombe sur
  // la premiere option et la valeur enregistree disparait sans un mot.
  if (!valeur) return;
  const connu = Array.from(liste.options).some((o) => o.value === String(valeur));
  if (connu) return;
  liste.value = '__libre__';
  if (champLibre) champLibre.value = valeur;
}

function ajouterSurMesure(liste, libelle) {
  const option = document.createElement('option');
  option.value = '__libre__';
  option.textContent = libelle;
  liste.appendChild(option);
}

function basculerSurMesure() {
  const tonLibre = $('ton').value === '__libre__';
  const volumeLibre = $('taille').value === '__libre__';
  $('ton-libre').hidden = !tonLibre;
  $('bloc-sur-mesure').hidden = !volumeLibre;
}

async function chargerProduits() {
  const reponse = await fetch('/api/produits');
  if (!reponse.ok) return;
  const donnees = await reponse.json();
  // Comparer le NOMBRE de produits suffisait tant que la liste ne faisait
  // que grandir. Une restauration la remplace : un atelier d'un produit
  // rendu a un autre atelier d'un produit laissait la page afficher
  // l'ancien, indefiniment. On compare donc ce qui est affiche.
  const empreinte = donnees.produits.map((p) => p.id).join('|');
  if (empreinte === etat.produitsCharges) return;
  etat.produitsCharges = empreinte;

  if (!donnees.produits.length) {
    $('produits').innerHTML = "<span class='vide'>Aucun produit pour l'instant.</span>";
    return;
  }
  $('produits').innerHTML = donnees.produits.map((p) => {
    const date = new Date(p.cree_le * 1000).toLocaleString('fr-FR',
      { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
    const liens = p.fichiers.map((f) =>
      `<a href="${echapper(f.url)}" target="_blank" rel="noopener">${echapper(f.nom)}</a>`
    ).join('');
    const note = p.note ? ` &middot; qualite ${p.note}/10` : '';
    return `<div class="produit">
      <div class="titre">${echapper(p.titre)}</div>
      <div class="meta">${echapper(p.type)} &middot; ${date}${
        p.mots ? ' &middot; ' + p.mots + ' mots' : ''}${note}</div>
      <div class="fichiers">${liens}</div></div>`;
  }).join('');
}

/* --------------------------------------------------- commerce et doublons */
async function chargerCommerce() {
  const reponse = await fetch('/api/commerce');
  if (!reponse.ok) return;
  const d = await reponse.json();
  afficherVentes(d);
  afficherDoublons(d);
}

function afficherVentes(d) {
  const aDesVentes = (d.devises || []).length > 0;
  $('commerce-vide').hidden = aDesVentes;
  $('commerce-chiffres').hidden = !aDesVentes;
  $('commerce-produits').hidden = !aDesVentes;
  $('commerce-prix').hidden = !aDesVentes;
  if (!aDesVentes) return;

  // Une devise par bloc : elles ne sont jamais additionnees, parce que
  // convertir sans source de taux reviendrait a fabriquer le resultat.
  $('commerce-chiffres').innerHTML = d.devises.map((t) => {
    const net = t.net_inconnu
      ? '<span class="note">net inconnu sur ' + t.net_inconnu + ' ligne(s)</span>'
      : '<span class="note">net ' + (t.net || 0).toFixed(2) + '</span>';
    return `<div class="bloc">
      <div class="valeur">${(t.brut || 0).toFixed(2)} ${echapper(t.devise)}</div>
      <div class="libelle">${t.unites || 0} unites vendues</div>
      ${net}</div>`;
  }).join('');

  const produits = d.produits || [];
  const maximum = produits.reduce((m, p) => Math.max(m, p.brut || 0), 0) || 1;
  $('commerce-produits').innerHTML = produits.map((p) => `
    <div class="ligne-vente">
      <div class="haut">
        <span class="nom">${echapper(p.titre || p.produit_id)}</span>
        <span class="montant">${(p.brut || 0).toFixed(2)} ${echapper(p.devise)}</span>
      </div>
      <div class="piste"><span style="width:${
        Math.max(3, Math.round((p.brut || 0) / maximum * 100))}%"></span></div>
    </div>`).join('');

  const prix = (d.prix || []).filter((x) => x.ventes >= 3);
  $('commerce-prix').innerHTML = prix.length
    ? prix.map((x) => `Prix median reellement encaisse : <strong>${
        x.median.toFixed(2)} ${echapper(x.devise)}</strong> (${x.ventes} ventes,
        moitie centrale ${x.bas.toFixed(2)} a ${x.haut.toFixed(2)})`).join('<br/>')
    : 'Moins de trois ventes : pas encore de prix median a montrer.';
}

function afficherDoublons(d) {
  // « Aucun recouvrement » se lit comme une bonne nouvelle. Ce peut etre
  // « rien n'a ete compare » : les empreintes sont posees a la fabrication,
  // et un catalogue plus ancien n'en a aucune.
  const manquantes = d.sans_empreinte || 0;
  $('doublons-manquants').hidden = manquantes === 0;
  $('doublons-manquants').textContent = manquantes
    ? `${manquantes} produit(s) sans empreinte : ils ne sont compares a rien.`
    : '';
  $('doublons-reconstruire').hidden = manquantes === 0;

  const paires = d.doublons || [];
  if (!paires.length) {
    $('doublons').innerHTML = d.produits_compares > 1
      ? `<span class="vide">${d.produits_compares} produits compares,
         aucun recouvrement notable.</span>`
      : `<span class="vide">Moins de deux produits : rien a comparer.</span>`;
    return;
  }
  $('doublons').innerHTML = paires.map((p) => `
    <div class="doublon">
      <div class="paire">${echapper(p.un)}<br/>
        <span style="opacity:.7">et</span> ${echapper(p.autre)}</div>
      <div class="mesure">${echapper(p.motif)} commun &middot; ${
        Math.round(p.texte * 100)} % de texte, ${
        Math.round(p.plan * 100)} % de plan &middot; ${echapper(p.type)}</div>
    </div>`).join('');
}

/* ---------------------------------------------------------- usine continue */
const ETIQUETTES = {
  en_attente: 'en file', en_cours: 'en cours', fait: 'livre',
  echec: 'echec', annule: 'annule',
};

async function chargerUsine() {
  const reponse = await fetch('/api/usine');
  if (!reponse.ok) return;
  const etat = await reponse.json();
  const zone = $('usine-etat');

  if (etat.en_marche) {
    const courant = etat.session?.courant;
    zone.className = 'etat marche';
    zone.textContent = courant
      ? `En marche — ${courant.type} : « ${courant.sujet} » (${etat.session.nombre_faits || 0} livre(s))`
      : `En marche — ${etat.session?.nombre_faits || 0} produit(s) livre(s)`;
  } else {
    zone.className = 'etat';
    const compte = etat.file;
    zone.textContent = compte.en_attente
      ? `A l'arret — ${compte.en_attente} niche(s) en attente`
      : "A l'arret — file vide";
  }
  $('usine-demarrer').disabled = etat.en_marche;
  $('usine-arreter').disabled = !etat.en_marche;

  const b = etat.budget;
  $('usine-budget').textContent = b.actif && b.appels_jour_max
    ? `Budget : ${b.appels_jour} / ${b.appels_jour_max} appels aujourd'hui`
      + (b.produits_jour_max ? ` · ${b.produits_faits} / ${b.produits_jour_max} produits` : '')
    : "Aucun budget defini — reglez-le avec « usine reglages ».";

  const entrees = etat.prochaines || [];
  $('file-liste').innerHTML = entrees.length
    ? entrees.map((e) => `<div class="entree en_attente">
        <span class="etiquette">${ETIQUETTES.en_attente}</span>
        <span class="sujet">${echapper(e.sujet)}</span>
        <button data-retirer="${e.id}" title="Retirer">&times;</button>
      </div>`).join('')
    : '<span class="vide">Aucune niche en attente.</span>';
}

$('file-liste').addEventListener('click', async (evenement) => {
  const identifiant = evenement.target.dataset?.retirer;
  if (!identifiant) return;
  await envoyerFile({ action: 'retirer', id: Number(identifiant) });
});

async function envoyerFile(charge) {
  const reponse = await fetch('/api/file', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(charge),
  });
  const donnees = await reponse.json();
  if (donnees.erreur) ajouterLigne('file : ' + echapper(donnees.erreur), 'souci');
  chargerUsine();
  return donnees;
}

$('file-ajouter').addEventListener('click', async () => {
  const sujet = $('sujet').value.trim();
  if (!sujet) { $('sujet').focus(); return; }
  const donnees = await envoyerFile({
    action: 'ajouter', sujet, type: $('type').value,
    nombre: $('nombre').value, audience: $('audience').value.trim(),
    ton: $('ton').value === '__libre__'
      ? $('ton-libre').value.trim() : $('ton').value,
    qualite: $('qualite').value,
  });
  if (donnees.doublon) ajouterLigne('deja en file : ' + echapper(sujet), 'souci');
  else if (donnees.ajoute) {
    ajouterLigne('ajoute a la file : ' + echapper(sujet), 'succes');
    $('sujet').value = '';
  }
});

$('file-rejouer').addEventListener('click', () => envoyerFile({ action: 'rejouer' }));

$('usine-demarrer').addEventListener('click', async () => {
  $('usine-demarrer').disabled = true;
  const reponse = await fetch('/api/usine', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action: 'demarrer', auto: $('usine-auto').checked }),
  });
  const donnees = await reponse.json();
  if (donnees.erreur) ajouterLigne('usine : ' + echapper(donnees.erreur), 'souci');
  else ajouterLigne('usine continue demarree', 'succes');
  chargerUsine();
});

$('usine-arreter').addEventListener('click', async () => {
  const reponse = await fetch('/api/usine', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action: 'arreter' }),
  });
  const donnees = await reponse.json();
  ajouterLigne(donnees.arret_demande
    ? "arret demande — le produit en cours se termine"
    : "aucune usine en marche", donnees.arret_demande ? 'succes' : 'souci');
  chargerUsine();
});

/* ------------------------------------------------------- flux temps reel */
function traiter(evenement) {
  etat.dernierEvenement = Math.max(etat.dernierEvenement, evenement.id || 0);

  if (evenement.type === 'agent') {
    const pastille = document.querySelector(`[data-agent="${evenement.agent}"]`);
    if (pastille) pastille.classList.toggle('actif', evenement.etat === 'debut');
    if (evenement.etat === 'debut') {
      scene.pulser(evenement.agent);
      $('etat-scene').textContent = 'Agent ' + evenement.agent + ' au travail';
    } else if (evenement.fournisseur) {
      scene.majEtat({ actifs: new Set([evenement.fournisseur]) });
      scene.jeton(evenement.fournisseur);
      ajouterLigne(
        `<span class="heure">${heure(evenement.ts)}</span> ` +
        `<span class="agent-nom">${echapper(evenement.agent)}</span> ` +
        `via ${echapper(evenement.fournisseur)}` +
        (evenement.tokens ? ` (${evenement.tokens} jetons)` : ''));
    }
  } else if (evenement.type === 'section') {
    etat.avancement = evenement.index || etat.avancement;
    etat.objectif = evenement.total || etat.objectif;
    scene.majEtat({ dalles: etat.avancement, objectif: etat.objectif });
    animerVers($('avancement'), etat.avancement);
    $('objectif').textContent = etat.objectif ? ' / ' + etat.objectif : '';
    $('etat-scene').textContent = evenement.titre || 'Production en cours';
  } else if (evenement.type === 'qualite') {
    if (evenement.etat === 'critique') {
      ajouterLigne(
        `<span class="heure">${heure(evenement.ts)}</span> relecture ` +
        `« ${echapper(evenement.intitule)} » : ${evenement.note}/10, ` +
        `${evenement.problemes} correction(s)`,
        evenement.note >= 7.5 ? 'succes' : 'souci');
      $('qualite-resume').textContent =
        `Derniere relecture : ${evenement.note}/10 (passe ${evenement.passe})`;
    }
  } else if (evenement.type === 'alerte') {
    ajouterLigne(`<span class="heure">${heure(evenement.ts)}</span> ` +
      `domaine sensible : ${echapper(evenement.domaine)}`, 'souci');
  } else if (evenement.type === 'journal') {
    ajouterLigne(`<span class="heure">${heure(evenement.ts)}</span> ` +
      echapper(evenement.message));
  } else if (evenement.type === 'usine') {
    chargerUsine();
    if (evenement.motif_fin) {
      ajouterLigne('usine arretee : ' + echapper(evenement.motif_fin), 'souci');
    }
  } else if (evenement.type === 'produit') {
    ajouterLigne(`<span class="heure">${heure(evenement.ts)}</span> ` +
      `produit termine : ${echapper(evenement.titre)}`, 'succes');
    $('etat-scene').textContent = 'Produit livre';
    chargerProduits();
    chargerCommerce();
  }
}

function brancherFlux() {
  if (!window.EventSource) { setInterval(sonder, 2500); return; }
  const source = new EventSource('/api/flux?depuis=' + etat.dernierEvenement);
  source.onmessage = (message) => {
    try { traiter(JSON.parse(message.data)); } catch (e) { /* trame partielle */ }
  };
  source.onerror = () => {
    source.close();
    // Reconnexion differee : le serveur peut etre occupe a produire.
    setTimeout(brancherFlux, 3000);
  };
}

/* Repli sans EventSource (vieux navigateurs Android). */
async function sonder() {
  const reponse = await fetch('/api/evenements?depuis=' + etat.dernierEvenement);
  if (!reponse.ok) return;
  const donnees = await reponse.json();
  donnees.evenements.forEach(traiter);
}

/* ------------------------------------------------------------- interactions */
function decrireType() {
  const choisi = (etat.types || []).find((t) => t.cle === $('type').value);
  if (!choisi) return;
  $('type-detail').textContent = `${choisi.detail} · ${choisi.duree}`;
  const champ = $('nombre');
  champ.placeholder = choisi.quantite ? String(choisi.defaut) : 'sans objet';
  champ.disabled = !choisi.quantite;
}

$('type').addEventListener('change', () => {
  $('bloc-reseau').hidden = $('type').value !== 'social';
  decrireType();
});

let minuterieAlerte = null;
$('sujet').addEventListener('input', () => {
  clearTimeout(minuterieAlerte);
  minuterieAlerte = setTimeout(async () => {
    const sujet = $('sujet').value.trim();
    if (sujet.length < 6) { $('alerte-sujet').hidden = true; return; }
    const reponse = await fetch('/api/verifier-sujet',
      { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sujet }) });
    if (!reponse.ok) return;
    const donnees = await reponse.json();
    if (!donnees.alertes.length) { $('alerte-sujet').hidden = true; return; }
    $('alerte-sujet').hidden = false;
    $('alerte-sujet').innerHTML = donnees.alertes
      .map((a) => `<strong>${echapper(a.domaine)}</strong> — ${echapper(a.detail)}`)
      .join('<br/>');
  }, 600);
});

$('theme').addEventListener('click', () => {
  const jour = document.documentElement.dataset.theme === 'jour';
  document.documentElement.dataset.theme = jour ? 'nuit' : 'jour';
  $('theme').textContent = jour ? 'Jour' : 'Nuit';
  try { localStorage.setItem('usine-theme', jour ? 'nuit' : 'jour'); } catch (e) {}
});

$('lancer').addEventListener('click', async () => {
  const sujet = $('sujet').value.trim();
  if (!sujet) { $('sujet').focus(); return; }
  $('lancer').disabled = true;
  $('lancer').textContent = 'Fabrication en cours...';
  etat.avancement = 0;
  scene.majEtat({ dalles: 0, objectif: 0 });
  animerVers($('avancement'), 0);

  const reponse = await fetch('/api/fabriquer', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      type: $('type').value, sujet,
      audience: $('audience').value.trim(),
      ton: $('ton').value === '__libre__'
        ? $('ton-libre').value.trim() : $('ton').value,
      taille: $('taille').value === '__libre__' ? '' : $('taille').value,
      chapitres: $('chapitres').value, mots: $('mots').value,
      qualite: $('qualite').value,
      auteur: $('auteur').value.trim(), nombre: $('nombre').value,
      reseau: $('reseau').value,
    }),
  });
  const donnees = await reponse.json();
  if (donnees.travail) {
    etat.travail = donnees.travail;
    surveiller(donnees.travail);
  } else {
    relacher();
    ajouterLigne('erreur : ' + echapper(donnees.erreur || 'inconnue'), 'souci');
  }
});

function relacher() {
  $('lancer').disabled = false;
  $('lancer').textContent = 'Lancer la fabrication';
}

async function surveiller(identifiant) {
  const reponse = await fetch('/api/travaux/' + identifiant);
  if (!reponse.ok) { relacher(); return; }
  const travail = await reponse.json();
  if (travail.statut === 'en_cours') { setTimeout(() => surveiller(identifiant), 3000); return; }
  relacher();
  if (travail.statut === 'echec') {
    ajouterLigne('echec : ' + echapper(travail.erreur), 'souci');
  }
  chargerProduits();
}

/* ------------------------------------------------------- veille de niche */
$('veille-lancer').addEventListener('click', async () => {
  const niche = $('veille-niche').value.trim() || $('sujet').value.trim();
  if (!niche) { $('veille-niche').focus(); return; }
  $('veille-niche').value = niche;
  $('veille-lancer').disabled = true;
  $('veille-etat').textContent = 'consultation en cours — deux appels espaces...';
  const reponse = await fetch('/api/veille', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ sujet: niche, periode: $('veille-periode').value }),
  });
  const donnees = await reponse.json();
  if (donnees.erreur) {
    $('veille-lancer').disabled = false;
    $('veille-etat').textContent = donnees.erreur;
    return;
  }
  suivreVeille(donnees.veille);
});

async function suivreVeille(identifiant) {
  const reponse = await fetch('/api/veille/' + identifiant);
  if (!reponse.ok) { $('veille-lancer').disabled = false; return; }
  const consultation = await reponse.json();
  if (consultation.statut === 'en_cours') {
    setTimeout(() => suivreVeille(identifiant), 2000);
    return;
  }
  $('veille-lancer').disabled = false;
  if (consultation.statut === 'echec') {
    $('veille-etat').textContent = consultation.erreur;
    return;
  }
  afficherVeille(consultation.resultat);
}

function afficherVeille(r) {
  if (r.indisponible) {
    // Une niche muette sur Reddit n'est pas une niche morte : c'est une
    // absence de mesure, et le tableau de bord doit le dire ainsi.
    $('veille-etat').textContent = r.indisponible;
    $('veille-resultat').hidden = true;
    return;
  }
  $('veille-etat').textContent = `${r.discussions.length} discussion(s), ${
    r.douleurs.length} formulation(s) de probleme.`;
  $('veille-resultat').hidden = false;

  $('veille-communautes').innerHTML = r.communautes.map((c) => c.lien
    ? `<a href="${echapper(c.lien)}" target="_blank" rel="noopener noreferrer"
         >r/${echapper(c.nom)}</a>`
    : `<span>r/${echapper(c.nom)}</span>`).join('');

  $('veille-mots').innerHTML = r.mots.map(([mot, n]) =>
    `<span>${echapper(mot)} <span class="nombre">${n}</span></span>`).join('');

  $('veille-titre-douleurs').hidden = r.douleurs.length === 0;
  $('veille-douleurs').innerHTML = r.douleurs.slice(0, 10)
    .map((d) => ligneDite(d, 'douleur')).join('');
  $('veille-discussions').innerHTML = r.discussions.slice(0, 12)
    .map((d) => ligneDite(d, '')).join('');
}

function ligneDite(d, classe) {
  // Le titre vient d'un flux exterieur : il est echappe, et son lien a deja
  // ete filtre cote serveur (https, reddit.com, rien d'autre).
  const titre = echapper(d.titre);
  const propos = d.lien
    ? `<a href="${echapper(d.lien)}" target="_blank" rel="noopener noreferrer"
        >${titre}</a>`
    : titre;
  return `<div class="dit ${classe}">
    <div class="propos">${propos}
      <span class="ou">r/${echapper(d.communaute)}</span></div>
    <button class="discret" data-sujet="${titre}">&rarr; sujet</button>
  </div>`;
}

// Un titre trouve doit pouvoir devenir un produit sans recopie : c'est tout
// l'interet de regarder ce que les gens disent.
document.addEventListener('click', (evenement) => {
  const propose = evenement.target.dataset?.sujet;
  if (!propose) return;
  $('sujet').value = propose;
  $('sujet').scrollIntoView({ behavior: 'smooth', block: 'center' });
  $('sujet').focus();
  // Le controle des domaines sensibles est branche sur « input » : un sujet
  // pose par programme doit y passer comme un sujet tape a la main.
  $('sujet').dispatchEvent(new Event('input'));
});

/* --------------------------------------------------- empreintes manquantes */
$('doublons-reconstruire').addEventListener('click', async () => {
  $('doublons-reconstruire').disabled = true;
  $('doublons-etat').textContent = 'lecture des fichiers sur le disque...';
  const reponse = await fetch('/api/doublons', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action: 'reconstruire' }),
  });
  const d = await reponse.json();
  $('doublons-reconstruire').disabled = false;
  if (d.erreur) { $('doublons-etat').textContent = d.erreur; return; }
  const reste = d.reste
    ? ` ${d.reste} sans texte relisible (dossier deplace ou type sans texte).`
    : '';
  $('doublons-etat').textContent = `${d.reconstruites} empreinte(s) posee(s).${reste}`;
  chargerCommerce();
});

/* ----------------------------------------------------- sauvegarde */
async function chargerSauvegardes() {
  const reponse = await fetch('/api/sauvegardes');
  if (!reponse.ok) return;
  afficherSauvegardes((await reponse.json()).archives);
}

function afficherSauvegardes(archives) {
  if (!archives.length) {
    $('sauvegardes').innerHTML =
      '<span class="vide">Aucune archive pour l\'instant.</span>';
    return;
  }
  $('sauvegardes').innerHTML = archives.map((a) => `
    <div class="archive">
      <span class="nom">${echapper(a.nom)}</span>
      <span class="quand">${a.ko} Ko &middot; ${dateCourte(a.ts)}</span>
      <a href="/archive/${encodeURIComponent(a.nom)}" download>Telecharger</a>
      <button class="discret refaire" data-restaurer="${echapper(a.nom)}"
        >Restaurer</button>
    </div>`).join('');
}

function dateLisible(iso) {
  // La fiche d'archive porte un horodatage ISO en UTC. Lu tel quel sur un
  // telephone, il ne dit pas grand-chose de « hier soir ».
  const quand = new Date(iso);
  if (!iso || Number.isNaN(quand.getTime())) return '?';
  return quand.toLocaleString('fr-FR', { dateStyle: 'long', timeStyle: 'short' });
}

function dateCourte(ts) {
  return new Date(ts * 1000).toLocaleString('fr-FR',
    { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
}

$('sauvegarde-creer').addEventListener('click', async () => {
  $('sauvegarde-creer').disabled = true;
  $('sauvegarde-etat').textContent = 'copie de la base en cours...';
  const reponse = await fetch('/api/sauvegarde', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action: 'creer',
                           avec_produits: $('sauvegarde-produits').checked }),
  });
  const d = await reponse.json();
  $('sauvegarde-creer').disabled = false;
  if (d.erreur) { $('sauvegarde-etat').textContent = d.erreur; return; }
  $('sauvegarde-etat').textContent =
    `${echapper(d.archive.nom)} — ${d.archive.ko} Ko. Telechargez-la.`;
  afficherSauvegardes(d.sauvegardes);
});

/* ------------------------------------------------------------ restauration */
// Remplacer l'atelier se demande en deux temps : d'abord regarder ce que
// contient l'archive, ensuite seulement l'installer. Un seul geste separant
// « je consulte mes sauvegardes » de « j'efface aujourd'hui » serait trop
// peu, surtout au pouce sur un telephone.
let archiveAremettre = '';

$('sauvegardes').addEventListener('click', async (evenement) => {
  const nom = evenement.target.dataset?.restaurer;
  if (!nom) return;
  const reponse = await fetch('/api/sauvegarde', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action: 'inspecter', nom }),
  });
  const fiche = await reponse.json();
  if (fiche.erreur || !fiche.valide) {
    $('sauvegarde-etat').textContent = fiche.erreur || fiche.probleme;
    return;
  }
  archiveAremettre = nom;
  $('restauration-fiche').innerHTML = `
    <strong>${echapper(nom)}</strong><br/>
    Ecrite le ${echapper(dateLisible(fiche.cree_le))} &middot; schema ${
      fiche.schema} (l'usine en est a ${fiche.schema_courant})<br/>
    ${fiche.avec_reglages ? 'Reglages inclus' : 'Sans les reglages'} &middot; ${
      fiche.fichiers_produits} fichier(s) de produits`;
  $('restauration-compris').checked = false;
  $('restauration-faire').disabled = true;
  $('restauration').hidden = false;
  $('restauration').scrollIntoView({ behavior: 'smooth', block: 'center' });
});

$('restauration-compris').addEventListener('change', () => {
  $('restauration-faire').disabled = !$('restauration-compris').checked;
});

$('restauration-annuler').addEventListener('click', () => {
  archiveAremettre = '';
  $('restauration').hidden = true;
});

$('restauration-faire').addEventListener('click', async () => {
  if (!archiveAremettre || !$('restauration-compris').checked) return;
  $('restauration-faire').disabled = true;
  $('sauvegarde-etat').textContent = 'restauration en cours...';
  const reponse = await fetch('/api/sauvegarde', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    // La confirmation voyage avec la requete : le serveur ne se fie pas a
    // l'etat d'une page qu'il ne voit pas.
    body: JSON.stringify({ action: 'restaurer', nom: archiveAremettre,
                           confirme: true }),
  });
  const d = await reponse.json();
  if (d.erreur) {
    $('restauration-faire').disabled = false;
    $('sauvegarde-etat').textContent = d.erreur;
    return;
  }
  $('restauration').hidden = true;
  archiveAremettre = '';
  const mise = d.ancienne_base
    ? ` L'ancienne base est gardee sous ${echapper(d.ancienne_base)}.`
    : '';
  $('sauvegarde-etat').textContent =
    `Atelier restaure depuis ${echapper(d.nom)}.${mise}`;
  // Tout ce que la page affiche vient de la base qui vient d'etre remplacee.
  chargerProduits();
  chargerCommerce();
  chargerUsine();
  chargerSauvegardes();
  chargerEtat();
});

/* ----------------------------------------------------- archive televersee */
// Le plafond doit valoir celui du serveur : refuser ici evite d'envoyer
// cent megaoctets par le reseau du telephone pour se faire dire non.
const TELEVERSEMENT_MAX = 200 * 1024 * 1024;

$('archive-fichier').addEventListener('change', async () => {
  const fichier = $('archive-fichier').files[0];
  if (!fichier) return;
  const dire = (texte) => { $('televersement-etat').textContent = texte; };
  if (fichier.size > TELEVERSEMENT_MAX) {
    dire(`${Math.round(fichier.size / 1048576)} Mo : la limite est ${
      TELEVERSEMENT_MAX / 1048576} Mo.`);
    $('archive-fichier').value = '';
    return;
  }
  dire(`envoi de ${fichier.name}...`);
  let d;
  try {
    const reponse = await fetch(
      '/api/televerser?nom=' + encodeURIComponent(fichier.name),
      { method: 'POST', headers: { 'Content-Type': 'application/zip' },
        body: fichier });
    d = await reponse.json();
  } catch (e) {
    dire('transfert interrompu.');
    $('archive-fichier').value = '';
    return;
  }
  // Le champ est remis a zero dans tous les cas : sans cela, reprendre le
  // meme fichier apres une erreur ne declenche aucun evenement.
  $('archive-fichier').value = '';
  if (d.erreur) { dire(d.erreur); return; }
  dire(`${echapper(d.archive.nom)} recue — ${d.archive.ko} Ko, schema ${
    d.fiche.schema}. Elle est dans la liste ci-dessous.`);
  afficherSauvegardes(d.sauvegardes);
});

/* ---------------------------------------------------------------- demarrage */
try {
  const theme = localStorage.getItem('usine-theme');
  if (theme) {
    document.documentElement.dataset.theme = theme;
    $('theme').textContent = theme === 'jour' ? 'Nuit' : 'Jour';
  }
} catch (e) { /* stockage indisponible en navigation privee */ }

function boucle(t) { scene.rendre(t); requestAnimationFrame(boucle); }
if (scene.actif) requestAnimationFrame(boucle);

chargerEtat();
chargerProduits();
chargerUsine();
brancherFlux();
chargerCommerce();
chargerSauvegardes();
setInterval(chargerEtat, 15000);
setInterval(chargerCommerce, 30000);
setInterval(chargerUsine, 6000);
