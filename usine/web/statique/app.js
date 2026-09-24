/* Pilotage du tableau de bord : etat, flux temps reel, animation 3D. */
'use strict';

const $ = (id) => document.getElementById(id);
function effets3dActifs() {
  // Le reglage « effets_3d » (vieux telephone) coupe la 3D et le fond anime.
  // localStorage est le canal synchrone : la scene et « cyber.js » demarrent
  // avant que /api/etat reponde, donc on lit le choix deja persiste ici.
  try { return localStorage.getItem('usine-effets') !== 'off'; }
  catch (e) { return true; }
}
const SCENE_MUETTE = { actif: false, rendre() {}, pulser() {}, jeton() {},
                       majEtat() {} };
const scene = effets3dActifs() ? new SceneUsine($('toile')) : SCENE_MUETTE;
if (!scene.actif) $('scene').classList.add('sans-3d');
if (!effets3dActifs()) $('scene').hidden = true;

const etat = {
  types: [],
  travail: null, agents: {}, fournisseurs: [], avancement: 0, objectif: 0,
  peaux: [],
  dernierEvenement: 0, produitsCharges: null, produits: [],
  abOuvert: 0, abProduits: -1,
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

/* Les types, ranges par famille dans des groupes natifs.

   Une seule liste melangeait « Roman » entre « Pack de prompts » et
   « Sequence e-mail ». Ce n'est pas qu'une question d'ordre : les reglages
   qui s'affichent en dessous n'ont rien de commun d'une famille a l'autre,
   et passer de « niveau de chaleur » a « marge de reliure » dans le meme
   ecran donne l'impression d'un formulaire qui ne sait pas ce qu'il demande.

   « optgroup » plutot qu'une liste dessinee a la main : sur un telephone,
   c'est le selecteur natif d'Android qui s'ouvre, et lui sait deja afficher
   des groupes. */
const FAMILLES = [['fiction', 'Fiction'], ['pratique', 'Pratique']];

function remplirTypes(select, types, defaut) {
  const sans = types.filter((t) => !t.famille);
  const bloc = (liste) => liste
    .map((t) => `<option value="${echapper(t.cle)}"` +
                `${t.cle === defaut ? ' selected' : ''}>` +
                `${echapper(t.nom)}</option>`)
    .join('');
  const groupes = FAMILLES
    .map(([cle, titre]) => {
      const membres = types.filter((t) => t.famille === cle);
      /* Une famille vide ne laisse pas d'en-tete orphelin : le jour ou un
         type est retire, le groupe disparait avec lui. */
      return membres.length
        ? `<optgroup label="${titre}">${bloc(membres)}</optgroup>` : '';
    })
    .join('');
  select.innerHTML = bloc(sans) + groupes;
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

/* ------------------------------------------------------------- sections */
/* Le tableau de bord empilait treize cartes sur une seule page : il fallait
   faire defiler tout « Veille de niche » pour atteindre ses produits, et rien
   ne disait ce qui allait avec quoi. Les sections sont les MEMES que celles du
   menu Termux, dans le meme ordre — deux interfaces qui rangent les memes
   choses differemment obligent a apprendre deux fois.

   Le choix est retenu : on revient presque toujours sur la meme section, et
   la rouvrir a chaque rafraichissement serait le genre de petite friction
   qu'on ne signale jamais et qui fait abandonner. */
const SECTION_DEFAUT = 'fabriquer';

function sectionRetenue() {
  try { return localStorage.getItem('usine-section') || SECTION_DEFAUT; }
  catch (e) { return SECTION_DEFAUT; }
}

function montrerSection(cle) {
  const sections = document.querySelectorAll('.onglet');
  let connue = false;
  sections.forEach((s) => {
    const sien = s.dataset.section === cle;
    /* « hidden » et non « display:none » : une feuille de style qui ne charge
       pas laisserait les quatre sections empilees, c'est-a-dire exactement
       l'etat qu'on vient de corriger. */
    s.hidden = !sien;
    if (sien) connue = true;
  });
  if (!connue && cle !== SECTION_DEFAUT) { montrerSection(SECTION_DEFAUT); return; }
  document.querySelectorAll('#onglets button').forEach((b) => {
    const actif = b.dataset.onglet === cle;
    b.setAttribute('aria-selected', actif ? 'true' : 'false');
    b.classList.toggle('actif', actif);
    /* La barre defile maintenant sur une seule ligne : un onglet choisi au
       clavier, ou retenu du chargement precedent, peut se trouver hors du
       cadre — actif et invisible, ce qui se lit comme une page vide. */
    if (actif && b.scrollIntoView) {
      try { b.scrollIntoView({ block: 'nearest', inline: 'nearest' }); }
      catch (e) { /* vieux navigateur */ }
    }
  });
  /* La scene 3D ne dit qu'une chose : l'avancement d'une fabrication. Sur
     « Reglages » ou « La machine » elle ne dit rien, et elle mangeait 370px
     du haut de chaque onglet — sur un ecran de 915px, avant meme le premier
     champ. Elle reste la ou elle informe. */
  majVisibiliteScene();
  try { localStorage.setItem('usine-section', cle); } catch (e) { /* prive */ }
}

/* Les sections ou l'avancement d'une fabrication veut dire quelque chose. */
const SECTIONS_AVEC_SCENE = ['fabriquer', 'continue'];

function sceneAttendue() {
  let cle = '';
  try { cle = localStorage.getItem('usine-section') || SECTION_DEFAUT; }
  catch (e) { cle = SECTION_DEFAUT; }
  const active = document.querySelector('.onglet:not([hidden])');
  if (active && active.dataset.section) cle = active.dataset.section;
  return SECTIONS_AVEC_SCENE.indexOf(cle) !== -1;
}

/* Quatre conditions, et toutes doivent tenir : la section, la peau, le
   reglage « effets_3d » et le support WebGL. Une premiere version ne
   regardait que la derniere, et changer de peau ou d'onglet laissait la
   scene dans l'etat ou elle etait. */
function majVisibiliteScene() {
  const racine = document.documentElement;
  const anime = racine.dataset.anime !== 'non';
  $('scene').hidden = !(anime && scene.actif && effets3dActifs()
                        && sceneAttendue());
}

$('onglets').addEventListener('click', (evenement) => {
  const cle = evenement.target.dataset && evenement.target.dataset.onglet;
  if (cle) montrerSection(cle);
});
montrerSection(sectionRetenue());

/* --------------------------------------------------------------- chargement */
async function chargerEtat() {
  const reponse = await fetch('/api/etat');
  if (!reponse.ok) return;
  const donnees = await reponse.json();
  $('version').textContent = 'v' + donnees.version;

  /* Base illisible : le reste de la reponse n'existe pas, et l'afficher
     quand meme ferait une page a moitie peinte sans dire pourquoi. On montre
     la panne et le geste, une bonne fois. */
  if (donnees.base) {
    $('conseil').innerHTML = `Base de l'atelier illisible :
      ${echapper(donnees.base)}. Vos produits restent sur le disque.
      <code>${echapper(donnees.remede)}</code>`;
    $('jauges').innerHTML = '<span class="vide">diagnostic indisponible</span>';
    return;
  }

  etat.fournisseurs = donnees.fournisseurs.map((f) => f.nom);
  scene.majEtat({ fournisseurs: etat.fournisseurs });

  $('jauges').innerHTML = donnees.fournisseurs.map((f) => {
    // « aujourdhui » vaut null quand la base est illisible : la jauge reste
    // vide et affiche « ? », au lieu de montrer une journee vierge rassurante.
    const connu = f.aujourdhui !== null && f.aujourdhui !== undefined;
    const part = f.rpd && connu ? Math.min(100, (f.aujourdhui / f.rpd) * 100) : 0;
    const chaud = part > 75 ? ' chaud' : '';
    const etiquette = f.local ? 'local'
      : (f.disponible ? `${connu ? f.aujourdhui : '?'}/${f.rpd}` : 'sans cle');
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

  remplirPeaux(donnees.peaux, (function () {
    try { return localStorage.getItem('usine-theme'); } catch (e) { return null; }
  })() || (donnees.reglages || {}).theme || 'nuit');
  appliquerPeau($('theme').value || 'nuit');
  appliquerReglagesInterface(donnees.reglages);
  etat.groupesReglages = donnees.groupes_reglages || [];
  dessinerReglages(etat.groupesReglages, donnees.reglages || {});
  if (!$('ton').options.length) {
    etat.types = donnees.types;
    /* Le premier du catalogue, pas un nom ecrit ici : c'est le
       catalogue qui decide de l'ordre, et donc de ce qu'on propose
       d'abord. Un nom en dur survivrait au retrait du type. */
    remplirTypes($('type'), donnees.types, (donnees.types[0] || {}).cle);
    decrireType();
    remplirListe($('ton'), donnees.tons, donnees.reglages.ton);
    remplirListe($('taille'), donnees.tailles, donnees.reglages.taille);
    // Les listes sont des raccourcis, pas des limites : la derniere entree
    // ouvre la saisie libre.
    ajouterSurMesure($('ton'), 'autre...');
    ajouterSurMesure($('taille'), 'sur mesure...');
    preselectionner($('ton'), $('ton-libre'), donnees.reglages.ton);
    preselectionner($('taille'), $('chapitres'), donnees.reglages.taille);
    remplirSeries(donnees.series || []);
    $('ton').addEventListener('change', basculerSurMesure);
    $('taille').addEventListener('change', basculerSurMesure);
    basculerSurMesure();
    remplirListe($('qualite'), donnees.qualites, donnees.reglages.qualite);
    // Le choix du reseau est desormais un champ du type « social »,
    // bati depuis le catalogue : plus rien a remplir ici.
    decrireType();
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
  // Gardee meme si rien n'a change a l'ecran : la liste deroulante des
  // tests A/B s'en sert, et elle est construite ailleurs.
  etat.produits = donnees.produits;
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
    // La carte listait et servait les fichiers, sans savoir rien en faire —
    // alors que c'est le moment ou l'on veut le kit de vente ou l'archive.
    /* Un produit interrompu se presentait comme les autres. Il porte
       maintenant son etat et le bouton qui le finit — sans repayer ce qui
       est deja ecrit. */
    const inacheve = p.statut === 'en_cours';
    const reste = (p.manquants || []).length;
    const marque = inacheve
      ? `<span class="inacheve">inacheve${reste ? ' &middot; ' + reste
         + ' section(s) a finir' : ''}</span>` : '';
    return `<div class="produit${inacheve ? ' incomplet' : ''}">
      <div class="titre">${echapper(p.titre)}</div>
      <div class="meta">${echapper(p.type)} &middot; ${date}${
        p.mots ? ' &middot; ' + p.mots + ' mots' : ''}${note} ${marque}</div>
      <div class="fichiers">${liens}</div>
      <div class="rangee">
        ${inacheve ? `<button class="discret reprendre"
          data-reprendre="${echapper(p.id)}">Reprendre</button>` : `<button
          class="discret" data-livrer="${echapper(p.id)}">Archive ZIP</button>
        <button class="discret" data-marketing="${echapper(p.id)}">Kit de vente</button>`}
        <button class="discret refaire"
          data-supprimer="${echapper(p.id)}">Effacer</button>
        <span class="aide" data-etat="${echapper(p.id)}" role="status"></span>
      </div></div>`;
  }).join('');
}

$('produits').addEventListener('click', async (evenement) => {
  const jeu = evenement.target.dataset || {};
  const identifiant = jeu.livrer || jeu.marketing || jeu.reprendre || jeu.supprimer;
  if (!identifiant) return;
  /* Effacer est irreversible : on le demande, ici et pas seulement cote
     serveur, parce qu'un clic sur un telephone se fait a cote du bouton
     voisin plus souvent qu'on ne le croit. */
  if (jeu.supprimer) {
    if (!window.confirm("Effacer ce produit et son dossier ? "
                        + "Cette action est definitive.")) return;
    evenement.target.disabled = true;
    const z = document.querySelector(`[data-etat="${identifiant}"]`);
    if (z) z.textContent = 'suppression...';
    try {
      const r = await fetch('/api/produit', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'supprimer', id: identifiant,
                               confirme: true }),
      });
      const d = await r.json();
      if (d.erreur) { evenement.target.disabled = false;
                      if (z) z.textContent = d.erreur; return; }
      etat.produitsCharges = '';   /* forcer le redessin de la liste */
      chargerProduits();
    } catch (e) {
      evenement.target.disabled = false;
      if (z) z.textContent = "l'usine n'a pas repondu.";
    }
    return;
  }
  const zone = () => document.querySelector(`[data-etat="${identifiant}"]`);
  const dire = (html) => { const z = zone(); if (z) z.innerHTML = html; };
  const rendre = () => {
    // Les DEUX boutons du produit, pas le premier trouve : « querySelector »
    // rendait toujours « Archive ZIP » et laissait « Kit de vente » gris.
    document.querySelectorAll(
      `[data-livrer="${identifiant}"], [data-marketing="${identifiant}"],`
      + `[data-reprendre="${identifiant}"], [data-supprimer="${identifiant}"]`)
      .forEach((b) => { b.disabled = false; });
  };
  evenement.target.disabled = true;
  const action = jeu.livrer ? 'livrer' : (jeu.reprendre ? 'reprendre' : 'marketing');
  dire({ livrer: 'empaquetage...', reprendre: 'reprise en cours...',
         marketing: 'redaction du kit de vente...' }[action]);
  let d;
  try {
    const reponse = await fetch('/api/produit', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: action, id: identifiant }),
    });
    d = await reponse.json();
  } catch (e) {
    // Sans ce filet, un serveur qui tombe laisse le bouton desactive et
    // l'utilisateur devant un « empaquetage... » qui ne finit jamais.
    rendre();
    dire("l'usine n'a pas repondu.");
    return;
  }
  if (d.erreur) { rendre(); dire(echapper(d.erreur)); return; }
  if (d.archive) {
    // L'archive est ecrite A COTE du dossier du produit, pas dedans : la
    // liste de fichiers ne la verra jamais. On donne donc le lien ici.
    rendre();
    dire(`<a href="${echapper(d.archive)}" download>Telecharger l'archive</a>
          &middot; ${d.ko} Ko`);
    return;
  }
  suivreKit(d.travail, identifiant, dire, rendre);
});

async function suivreKit(travail, identifiant, dire, rendre) {
  let t;
  try {
    const reponse = await fetch('/api/travaux/' + travail);
    if (!reponse.ok) { rendre(); return; }
    t = await reponse.json();
  } catch (e) { rendre(); dire("l'usine n'a pas repondu."); return; }
  if (t.statut === 'en_cours') {
    setTimeout(() => suivreKit(travail, identifiant, dire, rendre), 3000);
    return;
  }
  rendre();
  if (t.statut === 'echec') { dire(echapper(t.erreur)); return; }
  /* Deux formes de resultat passent par ici : le kit de vente rend des
     fichiers, la reprise rend l'etat du produit. Lire « fichiers » sans
     verifier laissait la reprise sur une erreur de script, bouton rendu et
     rien affiche — alors que la reprise, elle, avait reussi. */
  const r = t.resultat || {};
  if (r.fichiers) {
    dire(r.fichiers.filter(Boolean).map((f) =>
      `<a href="${echapper(f)}" target="_blank" rel="noopener">${
        echapper(f.split('/').pop())}</a>`).join(' &middot; ')
      || 'kit de vente ecrit.');
    return;
  }
  const reste = (r.manquants || []).length;
  dire(reste ? `${reste} section(s) manquent encore.` : 'produit termine.');
  etat.produitsCharges = '';
  chargerProduits();
}

/* ------------------------------------------------------------- diagnostic */
$('docteur-lancer').addEventListener('click', async () => {
  $('docteur-lancer').disabled = true;
  $('docteur').innerHTML = '<span class="vide">verification en cours...</span>';
  const reponse = await fetch('/api/docteur');
  $('docteur-lancer').disabled = false;
  if (!reponse.ok) { $('docteur').innerHTML =
    '<span class="vide">diagnostic indisponible.</span>'; return; }
  const d = await reponse.json();
  const ligne = (bon, texte) =>
    `<div class="controle ${bon ? 'bon' : 'souci'}">${echapper(texte)}</div>`;
  const espace = d.espace.connu
    ? ligne(d.espace.libre_mo > 200, `Espace libre : ${d.espace.libre_mo} Mo`)
    : '';
  /* Le telephone : muet sur un PC, ou ces lignes n'apprendraient rien. */
  const tel = d.telephone || {};
  let telephone = '';
  if (tel.termux) {
    telephone = ligne(tel.api, tel.api
      ? 'termux-api present : notifications et garde batterie actives'
      : 'termux-api absent : ni notification, ni arret sur batterie faible');
    if (tel.batterie) {
      telephone += ligne(tel.batterie.niveau > 20 || tel.batterie.en_charge,
        `Batterie : ${tel.batterie.niveau} %`
        + (tel.batterie.en_charge ? ' (en charge)' : ''));
    }
  }
  $('docteur').innerHTML =
    `<div class="verdict-bloc ${d.verdict.etat === 'bloque' ? '' : 'gagnant'}">
       <strong>${echapper(d.verdict.etat)}</strong>
       <div>${echapper(d.verdict.message)}${d.verdict.remede
         ? `<br><code>${echapper(d.verdict.remede)}</code>` : ''}</div></div>`
    /* La base d'abord : quand elle ne se lit plus, les lignes suivantes
       decrivent une usine qui ne peut de toute facon rien enregistrer. */
    + (d.base ? ligne(false, 'Base illisible : ' + d.base) : '')
    + ligne(true, 'Python ' + d.python)
    + ligne(true, 'Atelier : ' + d.workdir)
    + ligne(d.env_present, d.env_present ? 'Fichier .env present'
        : 'Aucun fichier .env — lancez « usine cles »')
    + espace
    + telephone
    + ligne(d.reseau, d.reseau ? 'Reseau disponible'
        : 'Reseau indisponible — seule l\'IA locale fonctionnera')
    + ligne(d.node, d.node ? 'Node.js present : verification complete du JavaScript'
        : 'Node.js absent : JavaScript verifie en mode degrade')
    + (d.locaux.length
        ? ligne(true, 'IA locale : ' + d.locaux.join(', '))
        : ligne(true, 'Aucune IA locale detectee'));
});

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
    if (courant && courant.attente_jusqu_a) {
      // L'usine attend que les quotas reviennent — parfois jusqu'a minuit
      // UTC. Afficher « En marche » pendant des heures laissait croire a une
      // usine bloquee, et invitait a l'arreter au moment ou elle allait finir.
      const heure = new Date(courant.attente_jusqu_a * 1000).toLocaleTimeString(
        'fr-FR', {hour: '2-digit', minute: '2-digit'});
      zone.textContent = `En attente des fournisseurs — reprise automatique vers ${heure} : « ${courant.sujet} »`;
    } else {
      zone.textContent = courant
        ? `En marche — ${courant.type} : « ${courant.sujet} » (${etat.session.nombre_faits || 0} livre(s))`
        : `En marche — ${etat.session?.nombre_faits || 0} produit(s) livre(s)`;
    }
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

$('file-prospecter').addEventListener('click', async () => {
  /* Le jumeau manuel de « trouver les niches toute seule » : sans lui, la
     seule facon de remplir la file sans rien taper etait de lancer la boucle
     continue — donc de produire, alors qu'on voulait juste voir ce que
     l'usine propose. */
  $('file-prospecter').disabled = true;
  $('file-prospecter').textContent = 'recherche...';
  const donnees = await envoyerFile({ action: 'prospecter' });
  if (donnees.travail) surveiller(donnees.travail);
  $('file-prospecter').disabled = false;
  $('file-prospecter').textContent = 'Trouver des niches maintenant';
});

$('file-prospecter-fiction').addEventListener('click', async () => {
  /* Le bouton jumeau, et il ne pose pas la meme question. Une fiction ne se
     cherche pas comme une niche : le lecteur n'achete pas la solution d'un
     probleme, il achete un sous-genre, des tropes et une fin qu'on ne lui
     refuse pas. Sans ce bouton, cette recherche n'existait qu'en ligne de
     commande — donc pas pour qui pilote l'usine depuis son telephone. */
  const bouton = $('file-prospecter-fiction');
  bouton.disabled = true;
  bouton.textContent = 'recherche...';
  const donnees = await envoyerFile({ action: 'prospecter-fiction' });
  if (donnees.travail) surveiller(donnees.travail);
  bouton.disabled = false;
  bouton.textContent = 'Trouver des idées de fiction';
});

$('file-ajouter').addEventListener('click', async () => {
  const sujet = $('sujet').value.trim();
  /* Le champ « sujet » vit dans l'onglet « Fabriquer ». Y faire « focus() »
     depuis ici mettait le curseur dans une section CACHEE : le bouton
     semblait mort. On le dit, et on y emmene. */
  if (!sujet) {
    ajouterLigne('donnez un sujet dans l\'onglet « Fabriquer », ou utilisez '
      + '« Trouver des niches maintenant »', 'souci');
    montrerSection('fabriquer');
    ouvrirLesReglages();
    $('sujet').focus();
    return;
  }
  const donnees = await envoyerFile({
    action: 'ajouter', sujet, type: $('type').value,
    ...valeursDuType(), audience: $('audience').value.trim(),
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
  } else if (evenement.type === 'tronquee') {
    // Publie depuis toujours, affiche par personne : une reponse coupee au
    // plafond passait pour une reponse complete jusque chez l'acheteur.
    ajouterLigne(`<span class="heure">${heure(evenement.ts)}</span> ` +
      `reponse coupee au plafond (${echapper(evenement.fournisseur)}, ` +
      `${evenement.plafond} jetons) : le texte s'arrete avant sa fin`, 'souci');
  } else if (evenement.type === 'niche') {
    /* La niche que l'usine vient de choisir seule. Sans cette ligne,
       l'evenement partait dans le vide : on voyait « (l'usine choisit) »
       puis, d'un coup, un plan sur un sujet qu'on n'avait jamais lu. */
    ajouterLigne(`<span class="heure">${heure(evenement.ts)}</span> ` +
      `niche choisie : <strong>${echapper(evenement.sujet)}</strong>` +
      (evenement.source === 'file' ? ' (elle attendait en file)'
        : evenement.source === 'froid' ? ' (premiere niche de cet atelier)'
        : ''), 'succes');
  } else if (evenement.type === 'lecteur') {
    /* Tout le reste de l'usine juge le texte. Le lecteur dit s'il a compris,
       ce qui est la seule question a laquelle un acheteur repond vraiment. */
    ajouterLigne(`<span class="heure">${heure(evenement.ts)}</span> ` +
      `lecture par l'audience : clarte ${evenement.clarte ?? '?'}/10, ` +
      `${evenement.decrochages} decrochage(s)` +
      (evenement.promesse_tenue ? '' : ' &middot; <strong>promesse non tenue</strong>'),
      evenement.promesse_tenue && evenement.decrochages === 0 ? 'succes' : 'souci');
  } else if (evenement.type === 'deliberation') {
    /* Les sept agents ne se parlaient pas : l'editeur critiquait, le reviseur
       appliquait. Quand l'auteur conteste et qu'un tiers tranche, c'est la
       seule trace visible de l'echange — et la plus interessante, parce
       qu'une correction ECARTEE est une invention evitee. */
    ajouterLigne(`<span class="heure">${heure(evenement.ts)}</span> ` +
      `deliberation — « ${echapper(evenement.probleme)} » : ` +
      `${evenement.retenue ? 'correction maintenue' : 'ecartee'} ` +
      `(l'auteur objecte : ${echapper(evenement.objection)})`,
      evenement.retenue ? '' : 'succes');
  } else if (evenement.type === 'type_choisi') {
    /* Quand on demande « L'usine decide », le type n'est connu qu'ici. Sans
       cette ligne on voyait la fabrication demarrer sans jamais savoir de
       quoi — et les reglages du type, absents du formulaire par definition,
       ne pouvaient pas le dire non plus. */
    ajouterLigne(`<span class="heure">${heure(evenement.ts)}</span> ` +
      `type retenu par l'usine : <strong>${echapper(evenement.nom)}</strong>`,
      'succes');
  } else if (evenement.type === 'substitution') {
    /* Une reparation silencieuse est le genre de chose qui fait perdre une
       journee le jour ou elle cesse de suffire : l'usine dit quand elle
       change de modele, et pourquoi. */
    ajouterLigne(`<span class="heure">${heure(evenement.ts)}</span> ` +
      `${echapper(evenement.fournisseur)} ne sert plus ` +
      `« ${echapper(evenement.avant)} » : l'usine passe a ` +
      `« ${echapper(evenement.apres)} » (${echapper(evenement.role)})`, 'souci');
  } else if (evenement.type === 'controle') {
    ajouterLigne(`<span class="heure">${heure(evenement.ts)}</span> ` +
      `controle « ${echapper(evenement.intitule)} » : ${evenement.note}/10, ` +
      `${evenement.anomalies} anomalie(s)`,
      evenement.bloquantes ? 'souci' : '');
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
// « /api/reglages » etait servi et appele par personne : le tableau de bord
// affichait les reglages sans pouvoir les changer, et il fallait ressortir
// vers la ligne de commande pour retaper un nom d'auteur. Retenir ce qu'on
// vient de saisir est le geste qui manquait, et le seul qui manquait.
$('retenir').addEventListener('click', async () => {
  const choix = {
    auteur: $('auteur').value.trim(),
    audience: $('audience').value.trim(),
    ton: $('ton').value === '__libre__' ? $('ton-libre').value.trim() : $('ton').value,
    qualite: $('qualite').value,
  };
  if ($('taille').value !== '__libre__') choix.taille = $('taille').value;
  const reponse = await fetch('/api/reglages', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(choix),
  });
  const donnees = await reponse.json();
  const temoin = $('retenu');
  temoin.textContent = donnees.reglages ? 'enregistre' : 'echec';
  temoin.hidden = false;
  setTimeout(() => { temoin.hidden = true; }, 2500);
});

function remplirSeries(noms) {
  const liste = $('series-connues');
  if (!liste) return;
  liste.innerHTML = '';
  noms.forEach((nom) => {
    const choix = document.createElement('option');
    choix.value = nom;
    liste.appendChild(choix);
  });
}

function decrireType() {
  const choisi = (etat.types || []).find((t) => t.cle === $('type').value);
  if (!choisi) return;
  $('type-detail').textContent = `${choisi.detail} · ${choisi.duree}`;
  /* Le champ « Sections » est commun aux onze types, mais sa valeur par
     defaut ne l'est pas : trente scenes pour un roman, douze chapitres pour
     un ebook. Le placeholder le dit sans imposer. */
  if (choisi.quantite) $('chapitres').placeholder = String(choisi.defaut);
  dessinerChampsDuType(choisi);
}

/* Les reglages propres au type, batis depuis le catalogue.

   Ils etaient ecrits a la main dans le gabarit, avec des blocs caches et
   montres par ce script — un « bloc-reseau » pour les posts, un « bloc-serie »
   pour la fiction, et rien pour les autres. Mesure du 14/09/2026 : HUIT
   reglages sur dix-sept n'existaient plus que dans la ligne de commande. On ne
   pouvait pas choisir, depuis le navigateur, si un outil logiciel etait une
   ligne de commande ou une application web, ni combien de modules comptait une
   formation.

   Ajouter un type demandait d'editer le gabarit, ce script ET le serveur.
   Maintenant, un champ ajoute au catalogue apparait ici tout seul. */
/* Les reglages fins sont replies par defaut : le formulaire promet qu'on
   choisit un type et qu'on appuie. Trois chemins y renvoient pourtant le
   curseur — mettre le sujet saisi en file, reprendre un titre trouve par la
   veille, signaler un sujet manquant. Sans cette ligne, « focus() » visait un
   champ dans un bloc ferme : rien ne bougeait a l'ecran, exactement le defaut
   qu'on avait deja corrige quand le champ vivait dans un onglet cache. */
function ouvrirLesReglages() {
  const repli = $('reglages-fins');
  if (repli) repli.open = true;
}

function dessinerChampsDuType(type) {
  const carte = $('carte-type');
  /* UNE source : les champs declares au catalogue. Le catalogue porte aussi
     une « quantite » — la question que pose le menu Termux — et melanger les
     deux affichait deux fois le meme reglage : « Combien de modules » ET
     « Nombre de modules » sur la meme formation. */
  const tout = type.champs || [];
  carte.hidden = tout.length === 0;
  $('titre-type').textContent = `Réglages : ${type.nom}`;
  $('aide-type').textContent = tout.length
    ? `Ce que « ${type.nom} » comprend, et lui seul.` : '';
  $('champs-type').innerHTML = tout.map(champDuType).join('');
  /* Les series connues n'ont de sens que pour la fiction, et la liste arrive
     par « /api/etat » : on la rebranche apres avoir redessine. */
  const serie = document.getElementById('champ-serie');
  if (serie) serie.setAttribute('list', 'series-connues');
}

function champDuType(champ) {
  const id = 'champ-' + champ.nom;
  const aide = champ.aide
    ? `<small class="aide">${echapper(champ.aide)}</small>` : '';
  const unite = champ.unite ? ` <span class="unite">${echapper(champ.unite)}</span>` : '';
  if (champ.genre === 'booleen') {
    return `<label class="case" for="${id}">
      <input type="checkbox" id="${id}" data-champ="${echapper(champ.nom)}"
        ${champ.defaut ? 'checked' : ''}/>
      <span><span class="nom-reglage">${echapper(champ.libelle)}</span>
        ${aide}</span></label>`;
  }
  if (champ.genre === 'choix') {
    const options = (champ.choix || []).map((valeur) =>
      `<option value="${echapper(valeur)}"${
        valeur === champ.defaut ? ' selected' : ''}>${echapper(valeur)}</option>`
    ).join('');
    return `<label class="champ" for="${id}">${echapper(champ.libelle)}
      <select id="${id}" data-champ="${echapper(champ.nom)}">${options}</select>
      ${aide}</label>`;
  }
  const type = champ.genre === 'entier' || champ.genre === 'decimal'
    ? 'number' : 'text';
  const pas = champ.genre === 'decimal' ? ' step="0.5"' : '';
  const valeur = champ.defaut === 0 || champ.defaut ? champ.defaut : '';
  return `<label class="champ" for="${id}">${echapper(champ.libelle)}${unite}
    <input type="${type}"${pas} id="${id}" data-champ="${echapper(champ.nom)}"
      ${type === 'number' ? 'min="0"' : ''}
      placeholder="${echapper(String(valeur))}"/>
    ${aide}</label>`;
}

/* Ce que l'utilisateur a rempli dans la section du type, prêt pour l'envoi. */
function valeursDuType() {
  const valeurs = {};
  document.querySelectorAll('#champs-type [data-champ]').forEach((champ) => {
    const nom = champ.dataset.champ;
    if (champ.type === 'checkbox') {
      if (champ.checked) valeurs[nom] = true;
    } else if (String(champ.value).trim() !== '') {
      valeurs[nom] = champ.type === 'number' ? Number(champ.value) : champ.value;
    }
  });
  return valeurs;
}

$('type').addEventListener('change', decrireType);

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

$('theme').addEventListener('change', () => {
  appliquerPeau($('theme').value);
  try { localStorage.setItem('usine-theme', $('theme').value); } catch (e) {}
});

$('lancer').addEventListener('click', async () => {
  /* Un sujet vide n'est plus un refus, c'est une demande : « trouve-la ».
     L'ancienne version faisait « focus() » sur le champ et s'arretait la —
     aucun message, aucune erreur, rien dans le journal. On recliquait sur le
     bouton en croyant qu'il ne marchait pas. */
  const sujet = $('sujet').value.trim();
  $('lancer').disabled = true;
  $('lancer').textContent = sujet ? 'Fabrication en cours...'
                                  : 'Recherche de la niche...';
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
      auteur: $('auteur').value.trim(),
      // Les reglages propres au type, quels qu'ils soient : le formulaire
      // vient du catalogue, donc l'envoi aussi.
      ...valeursDuType(),
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
  if (!niche) {
    /* Muet auparavant : le bouton ne faisait rien et ne disait
       rien. Un champ vide a cote d'un bouton mort se lit comme
       une panne, pas comme une consigne. */
    $('veille-etat').textContent = 'donnez une niche a mesurer.';
    $('veille-niche').focus();
    return;
  }
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
  ouvrirLesReglages();
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
      fiche.fichiers_produits} fichier(s) de produits &middot; ${
      fiche.fichiers_invites || 0} invite(s) personnalisee(s)`;
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
  dire(`envoi de ${echapper(fichier.name)}...`);
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

/* ------------------------------------------------------------- marche */
$('marche-lancer').addEventListener('click', async () => {
  const sujet = $('veille-niche').value.trim() || $('sujet').value.trim();
  if (!sujet) {
    /* Muet auparavant : le bouton ne faisait rien et ne disait
       rien. Un champ vide a cote d'un bouton mort se lit comme
       une panne, pas comme une consigne. */
    $('veille-etat').textContent = 'donnez une niche a mesurer.';
    $('veille-niche').focus();
    return;
  }
  $('veille-niche').value = sujet;
  $('marche-lancer').disabled = true;
  $('veille-etat').textContent = 'mesure de quatre sources publiques...';
  const reponse = await fetch('/api/marche', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ sujet }),
  });
  const d = await reponse.json();
  if (d.erreur) {
    $('marche-lancer').disabled = false;
    $('veille-etat').textContent = d.erreur;
    return;
  }
  suivreMarche(d.marche);
});

async function suivreMarche(identifiant) {
  const reponse = await fetch('/api/marche/' + identifiant);
  if (!reponse.ok) { $('marche-lancer').disabled = false; return; }
  const sondage = await reponse.json();
  if (sondage.statut === 'en_cours') {
    setTimeout(() => suivreMarche(identifiant), 2000);
    return;
  }
  $('marche-lancer').disabled = false;
  if (sondage.statut === 'echec') {
    $('veille-etat').textContent = sondage.erreur;
    return;
  }
  afficherMarche(sondage.resultat);
}

function afficherMarche(r) {
  const lecture = r.lecture || {};
  $('marche-resultat').hidden = false;
  $('veille-etat').textContent = `${r.sources_disponibles.length} source(s) sur ${
    r.sources_disponibles.length + r.sources_indisponibles.length} ont repondu.`;
  const bloc = (libelle, valeur) => `<div class="bloc">
      <div class="valeur">${echapper(valeur || 'inconnu')}</div>
      <div class="libelle">${libelle}</div></div>`;
  $('marche-signaux').innerHTML =
    bloc('demande', lecture.demande) + bloc('concurrence', lecture.concurrence)
    + bloc('tendance', lecture.tendance);
  $('marche-details').innerHTML = (lecture.signaux || [])
    .map((ligne) => `<li>${echapper(ligne)}</li>`).join('');
  // Une source muette n'est pas un marche absent : ne pas le dire serait
  // laisser lire un verdict la ou il n'y a qu'une mesure manquante.
  $('marche-manques').textContent = r.sources_indisponibles.length
    ? 'Sans reponse : ' + r.sources_indisponibles.join(', ')
      + '. Ce silence ne mesure rien.'
    : '';
}

/* -------------------------------------------------------------- tests A/B */
async function chargerAb() {
  const reponse = await fetch('/api/ab');
  if (!reponse.ok) return;
  const d = await reponse.json();
  const produits = etat.produits || [];
  if (!$('ab-produit').options.length || etat.abProduits !== produits.length) {
    etat.abProduits = produits.length;
    $('ab-produit').innerHTML = '<option value="">sans produit</option>'
      + produits.map((p) => `<option value="${echapper(p.id)}">${
        echapper(p.titre || p.id)}</option>`).join('');
  }
  if (!d.tests.length) {
    $('ab-liste').innerHTML =
      '<span class="vide">Aucun test pour l\'instant.</span>';
    return;
  }
  $('ab-liste').innerHTML = d.tests.map((t) => `
    <div class="essai" data-essai="${t.id}">
      <div>
        <div class="nom">${echapper(t.titre)}</div>
        <div class="meta">${echapper(t.sujet)} &middot; ${
          t.nb_variantes} variantes &middot; ${echapper(t.statut)}</div>
      </div>
      <span class="verdict ${echapper(t.verdict)}">${echapper(t.verdict)}</span>
    </div>`).join('');
}

$('ab-liste').addEventListener('click', (evenement) => {
  const ligne = evenement.target.closest?.('[data-essai]');
  if (ligne) ouvrirAb(Number(ligne.dataset.essai));
});

async function ouvrirAb(identifiant) {
  const reponse = await fetch('/api/ab/' + identifiant);
  if (!reponse.ok) return;
  afficherAb(await reponse.json());
}

function afficherAb(d) {
  etat.abOuvert = d.id;
  const couverture = d.sujet === 'couverture';
  const variantes = d.variantes.map((v) => {
    const taux = v.vues ? (v.actions / v.vues * 100).toFixed(1) + ' %' : '—';
    const part = v.stats && v.stats.probabilite_meilleure != null
      ? `${Math.round(v.stats.probabilite_meilleure * 100)} % meilleure` : '';
    const rythme = v.rythme && v.rythme.periode
      ? `${v.rythme.ventes} vente(s) en ${v.rythme.jours} j`
      : (v.debut ? '' : 'sans periode');
    return `<div class="variante${d.gagnante === v.id ? ' gagnante' : ''}">
      ${v.image ? `<a href="${echapper(v.image)}" target="_blank" rel="noopener"
         ><img src="${echapper(v.image)}" alt="Variante ${echapper(v.etiquette)}"/></a>` : ''}
      <div class="corps">
        <div class="haut"><span class="lettre">${echapper(v.etiquette)}</span>
          <span class="texte">${echapper(v.contenu)}</span></div>
        ${v.angle ? `<div class="note">${echapper(v.angle)}</div>` : ''}
        <div class="note">${v.vues} vues &middot; ${v.actions} actions &middot; ${
          taux}${part ? ' &middot; ' + part : ''}${
          rythme ? ' &middot; ' + echapper(rythme) : ''}</div>
        <div class="rangee">
          <input type="number" min="0" placeholder="vues" data-vues="${v.id}"/>
          <input type="number" min="0" placeholder="actions" data-actions="${v.id}"/>
          <button class="discret" data-observer="${v.id}">Reporter</button>
        </div>
        <div class="rangee">
          <input type="date" value="${echapper(v.debut)}" data-du="${v.id}"/>
          <input type="date" value="${echapper(v.fin)}" data-au="${v.id}"/>
          <button class="discret" data-dater="${v.id}">Dater</button>
          <button class="discret" data-gagnante="${v.id}">Retenir</button>
        </div>
      </div>
    </div>`;
  }).join('');

  $('ab-detail').hidden = false;
  $('ab-detail').innerHTML = `
    <h3 class="sous">${echapper(d.titre)} — ${echapper(d.sujet)}</h3>
    <div class="verdict-bloc ${echapper(d.verdict.etat)}">
      <strong>${echapper(d.verdict.etat.toUpperCase())}</strong>
      <div>${echapper(d.verdict.message)}</div>
    </div>
    <div class="variantes${couverture ? ' avec-images' : ''}">${variantes}</div>
    ${d.sans_periode ? `<p class="aide">${d.sans_periode} variante(s) sans
      periode : elles ne peuvent recevoir aucune vente importee.</p>` : ''}
    ${d.rythme_probleme ? `<p class="aide">${echapper(d.rythme_probleme)}</p>` : ''}
    <div class="rangee">
      <button class="discret" data-fermer-ab="1">Fermer</button>
      <button class="discret refaire" data-supprimer-ab="${d.id}">Supprimer le test</button>
    </div>`;
  $('ab-detail').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

async function envoyerAb(charge) {
  const reponse = await fetch('/api/ab', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(charge),
  });
  const d = await reponse.json();
  $('ab-etat').textContent = d.erreur || '';
  return d;
}

$('ab-detail').addEventListener('click', async (evenement) => {
  const jeu = evenement.target.dataset || {};
  if (jeu.fermerAb) { $('ab-detail').hidden = true; return; }
  if (jeu.observer) {
    const vues = document.querySelector(`[data-vues="${jeu.observer}"]`).value;
    const actions = document.querySelector(`[data-actions="${jeu.observer}"]`).value;
    if (!vues && !actions) return;
    await envoyerAb({ action: 'observer', variante: Number(jeu.observer),
                      vues: Number(vues || 0), actions: Number(actions || 0) });
  } else if (jeu.dater) {
    const du = document.querySelector(`[data-du="${jeu.dater}"]`).value;
    if (!du) { $('ab-etat').textContent = 'une periode a besoin d\'un debut.'; return; }
    await envoyerAb({ action: 'periode', variante: Number(jeu.dater), du,
                      au: document.querySelector(`[data-au="${jeu.dater}"]`).value });
  } else if (jeu.gagnante) {
    await envoyerAb({ action: 'clore', id: etat.abOuvert,
                      gagnante: Number(jeu.gagnante) });
  } else if (jeu.supprimerAb) {
    await envoyerAb({ action: 'supprimer', id: Number(jeu.supprimerAb) });
    $('ab-detail').hidden = true;
    chargerAb();
    return;
  } else {
    return;
  }
  ouvrirAb(etat.abOuvert);
  chargerAb();
});

$('ab-creer').addEventListener('click', async () => {
  const produit = $('ab-produit').value;
  const titre = produit ? '' : $('sujet').value.trim();
  if (!produit && !titre) {
    $('ab-etat').textContent = 'choisissez un produit, ou ecrivez un titre '
      + 'dans le champ « Sujet » ci-dessus.';
    return;
  }
  $('ab-creer').disabled = true;
  $('ab-etat').textContent = 'generation des variantes...';
  const d = await envoyerAb({ action: 'creer', sur: $('ab-sur').value,
                              produit, titre });
  if (d.erreur) { $('ab-creer').disabled = false; return; }
  suivreAb(d.travail);
});

async function suivreAb(identifiant) {
  const reponse = await fetch('/api/travaux/' + identifiant);
  if (!reponse.ok) { $('ab-creer').disabled = false; return; }
  const travail = await reponse.json();
  if (travail.statut === 'en_cours') {
    setTimeout(() => suivreAb(identifiant), 2500);
    return;
  }
  $('ab-creer').disabled = false;
  if (travail.statut === 'echec') { $('ab-etat').textContent = travail.erreur; return; }
  const distinction = travail.resultat.distinction || {};
  $('ab-etat').textContent = distinction.testable === false
    ? 'Attention : ' + distinction.message : (distinction.message || 'Test pret.');
  await chargerAb();
  ouvrirAb(travail.resultat.experience_id);
}

/* ------------------------------------------------- ce que l'usine a appris */
async function chargerBilan() {
  const reponse = await fetch('/api/bilan');
  if (!reponse.ok) return;
  const b = await reponse.json();
  if (!b.productions) {
    $('bilan').innerHTML = `<span class="vide">${echapper(b.message)}</span>`;
    return;
  }
  const chiffre = (valeur, libelle) => `<div class="bloc">
      <div class="valeur">${echapper(valeur)}</div>
      <div class="libelle">${libelle}</div></div>`;
  const groupe = (titre, lignes) => !lignes || !lignes.length ? '' : `
    <h3 class="sous">${titre}</h3>
    <div class="barres">${lignes.map((g) => `
      <div class="ligne-vente"><div class="haut">
        <span class="nom">${echapper(g.valeur)}</span>
        <span class="montant">${g.note_moyenne}/10 &middot; ${
          g.productions} prod.</span></div>
        <div class="piste"><span style="width:${
          Math.max(3, Math.round(g.note_moyenne / 10 * 100))}%"></span></div>
      </div>`).join('')}</div>`;

  $('bilan').innerHTML =
    `<div class="chiffres">
       ${chiffre(b.productions, 'productions')}
       ${chiffre(b.note_moyenne != null ? b.note_moyenne + '/10' : '—', 'note moyenne')}
       ${chiffre(b.mots_totaux.toLocaleString('fr-FR'), 'mots produits')}
       ${chiffre(b.gain_moyen_relecture != null
         ? (b.gain_moyen_relecture > 0 ? '+' : '') + b.gain_moyen_relecture
         : '—', 'gain de relecture')}
     </div>`
    + groupe('Par type de produit', b.par_type)
    + groupe('Par ton', b.par_ton)
    + groupe('Par volume', b.par_taille)
    + groupe('Par niveau de qualite', b.par_qualite)
    + `<p class="aide">Un reglage n'apparait qu'a partir de deux productions
       notees : une seule ne mesure rien.</p>`;
}

/* --------------------------------------------- reglages -> interface */
/* Les reglages, tous, ranges comme le menu Termux les range. Le tableau de
   bord n'en montrait que huit sur vingt-six : les dix-huit autres — le
   contact imprime dans la notice de l'acheteur, la marque, les budgets qui
   arretent l'usine continue — n'existaient que dans un fichier JSON que
   personne n'ouvre. */
/* Repliables, et FERMES au depart sauf le premier. Les six groupes existaient
   deja, mais tous ouverts en meme temps : trente champs d'affilee dans une
   seule carte de 3900px. Un titre qui ne replie rien n'organise rien. */
function dessinerReglages(groupes, valeurs) {
  if (!groupes || !groupes.length) return;
  /* Ce que l'utilisateur a ouvert survit a un rafraichissement : la liste se
     redessine a chaque chargement d'etat, et refermer sous ses doigts le
     groupe qu'il etait en train de remplir serait pire que le mur. */
  const ouverts = new Set(
    Array.from(document.querySelectorAll('.groupe-reglages[open]'))
      .map((d) => d.dataset.groupe));
  const premier = ouverts.size ? null : (groupes[0] || {}).cle;
  $('reglages-groupes').innerHTML = groupes.map((g) => `
    <details class="groupe-reglages" data-groupe="${echapper(g.cle)}"${
      ouverts.has(g.cle) || g.cle === premier ? ' open' : ''}>
      <summary>${echapper(g.titre)}
        <span class="compte">${g.reglages.length}</span></summary>
      <div class="corps-groupe">
        <p class="aide">${echapper(g.aide)}</p>
        ${g.reglages.map((r) => champReglage(r, valeurs[r.nom])).join('')}
      </div>
    </details>`).join('');
}

function champReglage(reglage, valeur) {
  const id = 'reglage-' + reglage.nom;
  const etiquette = `<span class="nom-reglage">${echapper(reglage.nom)}</span>
    <small>${echapper(reglage.description)}</small>`;
  if (reglage.genre === 'booleen') {
    return `<label class="case" for="${id}">
      <input type="checkbox" id="${id}" data-reglage="${echapper(reglage.nom)}"
        ${valeur ? 'checked' : ''}/> ${etiquette}</label>`;
  }
  if (reglage.choix && reglage.choix.length) {
    const options = reglage.choix.map((c) =>
      `<option value="${echapper(c)}"${c === valeur ? ' selected' : ''}>${
        echapper(c)}</option>`).join('');
    return `<label class="champ" for="${id}">${etiquette}
      <select id="${id}" data-reglage="${echapper(reglage.nom)}">${options}</select>
      </label>`;
  }
  const type = reglage.genre === 'entier' ? 'number' : 'text';
  return `<label class="champ" for="${id}">${etiquette}
    <input type="${type}" id="${id}" data-reglage="${echapper(reglage.nom)}"
      value="${echapper(String(valeur === null || valeur === undefined ? '' : valeur))}"/>
    </label>`;
}

$('reglages-enregistrer').addEventListener('click', async () => {
  const envoi = {};
  document.querySelectorAll('[data-reglage]').forEach((champ) => {
    envoi[champ.dataset.reglage] = champ.type === 'checkbox'
      ? champ.checked
      : (champ.type === 'number' ? Number(champ.value) : champ.value);
  });
  $('reglages-etat').textContent = 'enregistrement...';
  try {
    const reponse = await fetch('/api/reglages', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(envoi),
    });
    const d = await reponse.json();
    if (d.erreur) { $('reglages-etat').textContent = d.erreur; return; }
    /* On redessine avec ce que le SERVEUR a retenu, pas avec ce qu'on lui a
       envoye : « qualite: rapidos » y devient « standard », et l'afficher tel
       qu'on l'a tape ferait croire a un reglage qui n'existe pas. */
    dessinerReglages(etat.groupesReglages, d.reglages || {});
    appliquerReglagesInterface(d.reglages || {});
    $('reglages-etat').textContent = 'enregistre.';
  } catch (e) {
    $('reglages-etat').textContent = "l'usine n'a pas repondu.";
  }
});

/* Les peaux viennent du serveur, qui les tient de usine/core/reglages.py.
   Les recopier ici en ferait une seconde liste, et c'est celle du navigateur
   qui vieillirait sans que rien ne le dise. */
function remplirPeaux(peaux, choisie) {
  if (!peaux || !peaux.length) return;
  etat.peaux = peaux;
  $('theme').innerHTML = peaux.map((p) =>
    `<option value="${echapper(p.cle)}" title="${echapper(p.description)}"${
      p.cle === choisie ? ' selected' : ''}>${echapper(p.nom)}</option>`).join('');
}

/* Une peau ne change pas que les couleurs. « papier », « console » et
   « contraste » coupent le fond anime et la scene 3D : le CSS seul ne peut
   pas arreter un canvas qui tourne, il faut le dire au script. */
function appliquerPeau(cle) {
  const racine = document.documentElement;
  racine.dataset.theme = cle;
  const fiche = (etat.peaux || []).find((p) => p.cle === cle);
  /* Le systeme d'exploitation a le dernier mot : quelqu'un qui a demande
     moins d'animations ne doit pas en recevoir parce qu'une peau en prevoit. */
  let anime = fiche ? fiche.anime !== false : true;
  try {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) anime = false;
  } catch (e) { /* vieux navigateur */ }
  racine.dataset.anime = anime ? 'oui' : 'non';
  const fond = document.getElementById('fond-cyber');
  if (fond) fond.hidden = !anime;
  /* Dans les DEUX sens. Une premiere version ne faisait que cacher : revenir
     d'une peau calme a « nuit » laissait la scene 3D eteinte jusqu'au
     rechargement, et on croyait la peau cassee. Le reglage « effets_3d »
     garde le dernier mot : une peau animee ne doit pas rallumer la 3D chez
     quelqu'un qui l'a coupee parce que son telephone rame. */
  majVisibiliteScene();
  if ($('theme').value !== cle) $('theme').value = cle;
}

function appliquerReglagesInterface(reglages) {
  if (!reglages) return;
  // Peau : le choix local prime ; sinon on suit le reglage.
  try {
    if (!localStorage.getItem('usine-theme') && reglages.theme) {
      appliquerPeau(reglages.theme);
    }
  } catch (e) { /* navigation privee */ }
  // Effets 3D : on persiste le choix pour les chargements suivants (pas de
  // flash), et on coupe tout de suite si c'est desactive.
  const veut = reglages.effets_3d !== false;
  try { localStorage.setItem('usine-effets', veut ? 'on' : 'off'); } catch (e) {}
  if (!veut) {
    $('scene').hidden = true;
    const fond = document.getElementById('fond-cyber');
    if (fond) fond.hidden = true;
  }
}

/* ---------------------------------------------------------------- demarrage */
try {
  const theme = localStorage.getItem('usine-theme');
  if (theme) document.documentElement.dataset.theme = theme;
} catch (e) { /* stockage indisponible en navigation privee */ }

function boucle(t) { scene.rendre(t); requestAnimationFrame(boucle); }
if (scene.actif) requestAnimationFrame(boucle);

chargerEtat();
chargerProduits();
chargerUsine();
brancherFlux();
chargerCommerce();
chargerSauvegardes();
chargerAb();
chargerBilan();
setInterval(chargerEtat, 15000);
setInterval(chargerCommerce, 30000);
setInterval(chargerBilan, 60000);
setInterval(chargerUsine, 6000);
