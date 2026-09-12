/* Fond anime du tableau de bord : grille en fuite facon Tron + pluie de
   glyphes. Pur canvas 2D, aucune dependance. Purement decoratif — le canvas
   est aria-hidden, ne capte aucun clic, et se coupe entierement sous
   « prefers-reduced-motion ». */
(function () {
  'use strict';
  var toile = document.getElementById('fond-cyber');
  if (!toile || !toile.getContext) return;

  var reduit = window.matchMedia
    && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (reduit) return;

  var ctx = toile.getContext('2d');
  var L = 0, H = 0, dpr = Math.min(window.devicePixelRatio || 1, 2);

  function theme() {
    // On lit les couleurs du theme en cours pour rester coherent avec le jour.
    var jour = document.documentElement.dataset.theme === 'jour';
    return jour
      ? { grille: 'rgba(0,141,158,0.20)', pluie: 'rgba(192,26,160,0.28)',
          horizon: 'rgba(0,141,158,0.30)' }
      : { grille: 'rgba(0,240,255,0.14)', pluie: 'rgba(255,43,214,0.30)',
          horizon: 'rgba(0,240,255,0.30)' };
  }

  function taille() {
    L = toile.clientWidth; H = toile.clientHeight;
    toile.width = Math.floor(L * dpr);
    toile.height = Math.floor(H * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    semerPluie();
  }

  // --- pluie de glyphes ---------------------------------------------------
  var GLYPHES = '01<>/[]{}=+*#$%&ｦｧｱｲｳｴｵﾉﾊﾋﾎﾏ';
  var colonnes = [];
  function semerPluie() {
    var pas = 16, nb = Math.floor(L / pas);
    colonnes = [];
    for (var i = 0; i < nb; i++) {
      colonnes.push({ x: i * pas, y: Math.random() * H,
                      v: 40 + Math.random() * 90 });
    }
  }

  var defile = 0, dernier = 0;
  function image(t) {
    var dt = Math.min((t - dernier) / 1000 || 0, 0.05);
    dernier = t;
    var c = theme();
    ctx.clearRect(0, 0, L, H);

    // Grille en perspective : des lignes horizontales qui accelerent vers le
    // bas, et des fuyantes vers un point de fuite haut-centre.
    defile = (defile + dt * 0.35) % 1;
    var fx = L / 2, fy = H * 0.12;
    ctx.strokeStyle = c.grille; ctx.lineWidth = 1;
    ctx.beginPath();
    for (var i = 0; i < 22; i++) {
      var p = ((i + defile) / 22);
      var y = fy + (H - fy) * p * p;              // espacement non lineaire
      ctx.moveTo(0, y); ctx.lineTo(L, y);
    }
    for (var j = -10; j <= 10; j++) {
      var bx = fx + (j / 10) * L * 1.4;
      ctx.moveTo(fx, fy); ctx.lineTo(bx, H);
    }
    ctx.stroke();

    // Ligne d'horizon lumineuse
    ctx.strokeStyle = c.horizon; ctx.lineWidth = 1.5;
    ctx.beginPath(); ctx.moveTo(0, fy); ctx.lineTo(L, fy); ctx.stroke();

    // Pluie de glyphes
    ctx.fillStyle = c.pluie;
    ctx.font = '13px "Courier New", monospace';
    for (var k = 0; k < colonnes.length; k++) {
      var col = colonnes[k];
      col.y += col.v * dt;
      if (col.y > H + 20) { col.y = -20; col.v = 40 + Math.random() * 90; }
      var g = GLYPHES[(Math.random() * GLYPHES.length) | 0];
      ctx.fillText(g, col.x, col.y);
    }
    requestAnimationFrame(image);
  }

  var minuteur;
  window.addEventListener('resize', function () {
    clearTimeout(minuteur); minuteur = setTimeout(taille, 150);
  });
  taille();
  requestAnimationFrame(image);
})();
