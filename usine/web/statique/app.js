/* Pilotage du tableau de bord : etat, flux temps reel, animation 3D. */
'use strict';

const $ = (id) => document.getElementById(id);
const scene = new SceneUsine($('toile'));
if (!scene.actif) $('scene').classList.add('sans-3d');

const etat = {
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
    remplirListe($('type'), donnees.types.map((t) => [t.cle, t.nom]), 'ebook');
    remplirListe($('ton'), donnees.tons, donnees.reglages.ton);
    remplirListe($('taille'), donnees.tailles, donnees.reglages.taille);
    remplirListe($('qualite'), donnees.qualites, donnees.reglages.qualite);
    remplirListe($('reseau'), donnees.reseaux, 'linkedin');
    $('auteur').value = donnees.reglages.auteur || '';
    $('audience').value = donnees.reglages.audience || '';
    $('agents').innerHTML = donnees.agents.map((a) =>
      `<span class="agent" data-agent="${a.nom}">
         <span class="pastille"></span>${echapper(a.nom)}</span>`).join('');
  }
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
  } else if (evenement.type === 'produit') {
    ajouterLigne(`<span class="heure">${heure(evenement.ts)}</span> ` +
      `produit termine : ${echapper(evenement.titre)}`, 'succes');
    $('etat-scene').textContent = 'Produit livre';
    chargerProduits();
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
$('type').addEventListener('change', () => {
  $('bloc-reseau').hidden = $('type').value !== 'social';
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
      audience: $('audience').value.trim(), ton: $('ton').value,
      taille: $('taille').value, qualite: $('qualite').value,
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
brancherFlux();
setInterval(chargerEtat, 15000);
