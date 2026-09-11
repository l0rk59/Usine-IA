/* Pilotage du tableau de bord : etat, flux temps reel, animation 3D. */
'use strict';

const $ = (id) => document.getElementById(id);
const scene = new SceneUsine($('toile'));
if (!scene.actif) $('scene').classList.add('sans-3d');

const etat = {
  types: [],
  travail: null, agents: {}, fournisseurs: [], avancement: 0, objectif: 0,
  dernierEvenement: 0, produitsCharges: 0,
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
  if (donnees.produits.length === etat.produitsCharges && etat.produitsCharges) return;
  etat.produitsCharges = donnees.produits.length;

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
setInterval(chargerEtat, 15000);
setInterval(chargerCommerce, 30000);
setInterval(chargerUsine, 6000);
