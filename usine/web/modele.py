"""Gabarit HTML du tableau de bord (une seule page, pensee pour un telephone)."""

PAGE = r"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover"/>
<title>Usine-IA</title>
<style>
:root { --fond:#0b0e14; --carte:#141923; --bord:#232a38; --encre:#e7eaf0;
        --doux:#96a0b3; --accent:#4f9cf9; --ok:#3ecf8e; --alerte:#f5a524;
        --erreur:#f6685e; }
@media (prefers-color-scheme: light) {
  :root { --fond:#f4f6fa; --carte:#ffffff; --bord:#e1e6ef; --encre:#161a22;
          --doux:#5d6779; --accent:#2563eb; }
}
* { box-sizing:border-box; -webkit-tap-highlight-color:transparent; }
body { margin:0; background:var(--fond); color:var(--encre);
  font:15px/1.55 -apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;
  padding-bottom:env(safe-area-inset-bottom); }
.enveloppe { max-width:44rem; margin:0 auto; padding:1rem 1rem 4rem; }
header { display:flex; align-items:baseline; gap:.6rem; padding:1.2rem 0 .4rem; }
h1 { font-size:1.4rem; margin:0; letter-spacing:-.02em; }
.version { color:var(--doux); font-size:.78rem; }
.carte { background:var(--carte); border:1px solid var(--bord); border-radius:14px;
  padding:1rem; margin-bottom:.9rem; }
h2 { font-size:.78rem; text-transform:uppercase; letter-spacing:.09em;
  color:var(--doux); margin:0 0 .8rem; font-weight:600; }
label { display:block; font-size:.8rem; color:var(--doux); margin:.7rem 0 .25rem; }
input, select, textarea, button { font:inherit; width:100%; border-radius:10px;
  border:1px solid var(--bord); background:var(--fond); color:var(--encre);
  padding:.62rem .7rem; }
textarea { min-height:4.5rem; resize:vertical; }
button { background:var(--accent); color:#fff; border:0; font-weight:600;
  padding:.8rem; margin-top:1rem; cursor:pointer; }
button:disabled { opacity:.55; cursor:progress; }
.duo { display:grid; grid-template-columns:1fr 1fr; gap:.6rem; }
.puces { display:flex; flex-wrap:wrap; gap:.35rem; }
.puce { font-size:.72rem; padding:.22rem .5rem; border-radius:999px;
  border:1px solid var(--bord); color:var(--doux); }
.puce.on { color:var(--ok); border-color:color-mix(in srgb, var(--ok) 40%, transparent); }
.puce.local { color:var(--alerte); border-color:color-mix(in srgb,var(--alerte) 40%,transparent); }
pre.journal { background:var(--fond); border:1px solid var(--bord); border-radius:10px;
  padding:.7rem; max-height:15rem; overflow:auto; font-size:.76rem; line-height:1.5;
  white-space:pre-wrap; word-break:break-word; margin:.6rem 0 0; }
.produit { border-top:1px solid var(--bord); padding:.75rem 0; }
.produit:first-of-type { border-top:0; }
.produit .titre { font-weight:600; }
.produit .meta { color:var(--doux); font-size:.76rem; margin:.15rem 0 .45rem; }
.fichiers { display:flex; flex-wrap:wrap; gap:.3rem; }
.fichiers a { font-size:.74rem; text-decoration:none; color:var(--accent);
  border:1px solid var(--bord); border-radius:8px; padding:.2rem .5rem; }
.etat { font-size:.8rem; color:var(--doux); }
.etat.travail { color:var(--accent); }
.etat.echec { color:var(--erreur); }
.vide { color:var(--doux); font-size:.85rem; }
.aide { color:var(--doux); font-size:.76rem; margin-top:.5rem; }
</style>
</head>
<body>
<div class="enveloppe">
<header><h1>Usine-IA</h1><span class="version">v{{VERSION}}</span></header>

<div class="carte">
  <h2>Fournisseurs IA</h2>
  <div class="puces" id="fournisseurs"><span class="vide">chargement...</span></div>
  <p class="aide" id="conseil"></p>
</div>

<div class="carte">
  <h2>Fabriquer un produit</h2>
  <label for="type">Type de produit</label>
  <select id="type">
    <option value="ebook">Ebook complet</option>
    <option value="prompts">Pack de prompts</option>
    <option value="formation">Mini-formation</option>
    <option value="outils">Boite a outils</option>
    <option value="social">Pack de publications</option>
    <option value="idees">Idees de produits</option>
  </select>

  <label for="sujet">Sujet</label>
  <textarea id="sujet" placeholder="ex : la prospection pour freelances debutants"></textarea>

  <label for="audience">Audience</label>
  <input id="audience" placeholder="ex : freelances qui demarrent"/>

  <div class="duo">
    <div><label for="ton">Ton</label><select id="ton"></select></div>
    <div><label for="taille">Volume</label><select id="taille"></select></div>
  </div>
  <div class="duo">
    <div><label for="auteur">Auteur</label><input id="auteur" value="Usine-IA"/></div>
    <div><label for="nombre">Quantite</label>
      <input id="nombre" type="number" min="0" placeholder="auto"/></div>
  </div>
  <div id="bloc-reseau" style="display:none">
    <label for="reseau">Reseau</label><select id="reseau"></select>
  </div>

  <button id="lancer">Lancer la fabrication</button>
  <p class="aide">La fabrication continue meme si vous fermez cette page.
    Comptez 3 a 20 minutes selon le volume.</p>
</div>

<div class="carte" id="carte-travail" style="display:none">
  <h2>Fabrication en cours</h2>
  <p class="etat travail" id="etat-travail"></p>
  <pre class="journal" id="journal"></pre>
</div>

<div class="carte">
  <h2>Produits</h2>
  <div id="produits"><span class="vide">chargement...</span></div>
</div>
</div>

<script>
const $ = (id) => document.getElementById(id);
let travailCourant = null;

function remplirListe(select, valeurs, defaut) {
  select.innerHTML = valeurs.map(v =>
    `<option value="${v}"${v === defaut ? ' selected' : ''}>${v}</option>`).join('');
}

async function chargerEtat() {
  const etat = await (await fetch('/api/etat')).json();
  $('fournisseurs').innerHTML = etat.fournisseurs.map(f => {
    const classe = f.disponible ? (f.local ? 'puce local' : 'puce on') : 'puce';
    const detail = f.disponible && !f.local ? ` ${f.aujourdhui}/${f.rpd}` : '';
    return `<span class="${classe}">${f.nom}${detail}</span>`;
  }).join('');
  $('conseil').textContent = etat.actifs > 0
    ? `${etat.actifs} fournisseur(s) distant(s) pret(s).`
    : "Aucune cle API detectee. Lancez « usine cles » dans Termux, ou demarrez une IA locale.";
  if (!$('ton').options.length) {
    remplirListe($('ton'), etat.tons, 'pro');
    remplirListe($('taille'), etat.tailles, 'standard');
    remplirListe($('reseau'), etat.reseaux, 'linkedin');
  }
}

async function chargerProduits() {
  const donnees = await (await fetch('/api/produits')).json();
  if (!donnees.produits.length) {
    $('produits').innerHTML = '<span class="vide">Aucun produit pour l\'instant.</span>';
    return;
  }
  $('produits').innerHTML = donnees.produits.map(p => {
    const date = new Date(p.cree_le * 1000).toLocaleString('fr-FR',
      { day:'2-digit', month:'2-digit', hour:'2-digit', minute:'2-digit' });
    const liens = p.fichiers.map(f =>
      `<a href="${f.url}" target="_blank" rel="noopener">${f.nom}</a>`).join('');
    return `<div class="produit"><div class="titre">${p.titre}</div>
      <div class="meta">${p.type} · ${date}${p.mots ? ' · ' + p.mots + ' mots' : ''}</div>
      <div class="fichiers">${liens}</div></div>`;
  }).join('');
}

async function suivre(id) {
  const travail = await (await fetch('/api/travaux/' + id)).json();
  if (travail.erreur && !travail.statut) return;
  $('carte-travail').style.display = 'block';
  $('journal').textContent = travail.journal.map(l => l.texte).join('\n');
  $('journal').scrollTop = $('journal').scrollHeight;
  const etat = $('etat-travail');
  if (travail.statut === 'en_cours') {
    const minutes = Math.round((Date.now() / 1000 - travail.debut) / 6) / 10;
    etat.className = 'etat travail';
    etat.textContent = `${travail.type} — « ${travail.sujet} » — ${minutes} min`;
    setTimeout(() => suivre(id), 2500);
  } else if (travail.statut === 'termine') {
    etat.className = 'etat';
    etat.textContent = 'Termine : ' + (travail.resultat?.titre || travail.sujet);
    $('lancer').disabled = false;
    $('lancer').textContent = 'Lancer la fabrication';
    chargerProduits();
  } else {
    etat.className = 'etat echec';
    etat.textContent = 'Echec : ' + travail.erreur;
    $('lancer').disabled = false;
    $('lancer').textContent = 'Lancer la fabrication';
  }
}

$('type').addEventListener('change', () => {
  $('bloc-reseau').style.display = $('type').value === 'social' ? 'block' : 'none';
});

$('lancer').addEventListener('click', async () => {
  const sujet = $('sujet').value.trim();
  if (!sujet) { $('sujet').focus(); return; }
  $('lancer').disabled = true;
  $('lancer').textContent = 'Fabrication en cours...';
  const reponse = await fetch('/api/fabriquer', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      type: $('type').value, sujet,
      audience: $('audience').value.trim(),
      ton: $('ton').value, taille: $('taille').value,
      auteur: $('auteur').value.trim(),
      nombre: $('nombre').value,
      reseau: $('reseau').value,
    }),
  });
  const donnees = await reponse.json();
  if (donnees.travail) { travailCourant = donnees.travail; suivre(donnees.travail); }
  else {
    $('lancer').disabled = false;
    $('lancer').textContent = 'Lancer la fabrication';
    alert(donnees.erreur || 'Erreur inconnue');
  }
});

chargerEtat();
chargerProduits();
setInterval(chargerEtat, 20000);
</script>
</body>
</html>
"""
