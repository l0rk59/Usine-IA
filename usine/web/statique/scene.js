/* Moteur 3D de l'Usine-IA — WebGL ecrit a la main.
 *
 * Aucune bibliotheque externe : le tableau de bord doit fonctionner hors ligne
 * sur un telephone, sans acces a un CDN. Repli automatique en canvas 2D si le
 * pilote WebGL du telephone refuse de compiler les nuanceurs.
 *
 * Ce que la scene represente :
 *   - le socle          : l'atelier ;
 *   - les orbes en orbite : les fournisseurs IA (ils s'allument quand ils repondent) ;
 *   - la colonne centrale : le produit en cours, une dalle par section terminee ;
 *   - les particules     : les jetons qui circulent du fournisseur vers le produit.
 */
'use strict';

/* ---------------------------------------------------------------- algebre */
const M4 = {
  identite: () => new Float32Array([1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1]),

  multiplier(a, b) {
    const r = new Float32Array(16);
    for (let l = 0; l < 4; l++) {
      for (let c = 0; c < 4; c++) {
        r[l * 4 + c] = a[l * 4] * b[c] + a[l * 4 + 1] * b[4 + c]
                     + a[l * 4 + 2] * b[8 + c] + a[l * 4 + 3] * b[12 + c];
      }
    }
    return r;
  },

  perspective(fovRad, aspect, proche, loin) {
    const f = 1 / Math.tan(fovRad / 2);
    const nf = 1 / (proche - loin);
    return new Float32Array([
      f / aspect, 0, 0, 0,
      0, f, 0, 0,
      0, 0, (loin + proche) * nf, -1,
      0, 0, 2 * loin * proche * nf, 0,
    ]);
  },

  regarder(oeil, cible, haut) {
    const z = V3.normaliser(V3.soustraire(oeil, cible));
    const x = V3.normaliser(V3.produit(haut, z));
    const y = V3.produit(z, x);
    return new Float32Array([
      x[0], y[0], z[0], 0,
      x[1], y[1], z[1], 0,
      x[2], y[2], z[2], 0,
      -V3.scalaire(x, oeil), -V3.scalaire(y, oeil), -V3.scalaire(z, oeil), 1,
    ]);
  },

  translation(x, y, z) {
    const m = M4.identite(); m[12] = x; m[13] = y; m[14] = z; return m;
  },

  echelle(x, y, z) {
    const m = M4.identite(); m[0] = x; m[5] = y; m[10] = z; return m;
  },

  rotationY(a) {
    const m = M4.identite(), s = Math.sin(a), c = Math.cos(a);
    m[0] = c; m[2] = -s; m[8] = s; m[10] = c; return m;
  },

  rotationX(a) {
    const m = M4.identite(), s = Math.sin(a), c = Math.cos(a);
    m[5] = c; m[6] = s; m[9] = -s; m[10] = c; return m;
  },

  /* Inverse-transposee 3x3, pour transformer correctement les normales
     quand l'objet est mis a l'echelle de facon non uniforme. */
  normale(m) {
    const a00=m[0],a01=m[1],a02=m[2], a10=m[4],a11=m[5],a12=m[6],
          a20=m[8],a21=m[9],a22=m[10];
    const b01 =  a22*a11 - a12*a21, b11 = -a22*a10 + a12*a20,
          b21 =  a21*a10 - a11*a20;
    let det = a00*b01 + a01*b11 + a02*b21;
    if (!det) return new Float32Array([1,0,0, 0,1,0, 0,0,1]);
    det = 1 / det;
    return new Float32Array([
      b01*det, (-a22*a01 + a02*a21)*det, ( a12*a01 - a02*a11)*det,
      b11*det, ( a22*a00 - a02*a20)*det, (-a12*a00 + a02*a10)*det,
      b21*det, (-a21*a00 + a01*a20)*det, ( a11*a00 - a01*a10)*det,
    ]);
  },
};

const V3 = {
  soustraire: (a, b) => [a[0]-b[0], a[1]-b[1], a[2]-b[2]],
  produit: (a, b) => [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]],
  scalaire: (a, b) => a[0]*b[0] + a[1]*b[1] + a[2]*b[2],
  normaliser(a) {
    const l = Math.hypot(a[0], a[1], a[2]) || 1;
    return [a[0]/l, a[1]/l, a[2]/l];
  },
};

/* -------------------------------------------------------------- geometrie */
function geometrieCube() {
  const p = [], n = [];
  const faces = [
    [[ 1,-1,-1],[ 1, 1,-1],[ 1, 1, 1],[ 1,-1, 1],[ 1, 0, 0]],
    [[-1,-1, 1],[-1, 1, 1],[-1, 1,-1],[-1,-1,-1],[-1, 0, 0]],
    [[-1, 1,-1],[-1, 1, 1],[ 1, 1, 1],[ 1, 1,-1],[ 0, 1, 0]],
    [[-1,-1, 1],[-1,-1,-1],[ 1,-1,-1],[ 1,-1, 1],[ 0,-1, 0]],
    [[-1,-1, 1],[ 1,-1, 1],[ 1, 1, 1],[-1, 1, 1],[ 0, 0, 1]],
    [[ 1,-1,-1],[-1,-1,-1],[-1, 1,-1],[ 1, 1,-1],[ 0, 0,-1]],
  ];
  for (const f of faces) {
    const s = f.slice(0, 4), normale = f[4];
    for (const i of [0, 1, 2, 0, 2, 3]) {
      p.push(s[i][0], s[i][1], s[i][2]);
      n.push(normale[0], normale[1], normale[2]);
    }
  }
  return { positions: new Float32Array(p), normales: new Float32Array(n),
           nb: p.length / 3, mode: 'TRIANGLES' };
}

function geometrieSphere(bandes = 14, secteurs = 20) {
  const p = [], n = [], grille = [];
  for (let b = 0; b <= bandes; b++) {
    const phi = b * Math.PI / bandes;
    for (let s = 0; s <= secteurs; s++) {
      const theta = s * 2 * Math.PI / secteurs;
      grille.push([
        Math.sin(phi) * Math.cos(theta),
        Math.cos(phi),
        Math.sin(phi) * Math.sin(theta),
      ]);
    }
  }
  const at = (b, s) => grille[b * (secteurs + 1) + s];
  for (let b = 0; b < bandes; b++) {
    for (let s = 0; s < secteurs; s++) {
      const a = at(b, s), d = at(b, s + 1), c = at(b + 1, s + 1), e = at(b + 1, s);
      for (const v of [a, d, c, a, c, e]) {
        p.push(v[0], v[1], v[2]); n.push(v[0], v[1], v[2]);
      }
    }
  }
  return { positions: new Float32Array(p), normales: new Float32Array(n),
           nb: p.length / 3, mode: 'TRIANGLES' };
}

function geometrieGrille(demi = 9, pas = 1) {
  const p = [], n = [];
  for (let i = -demi; i <= demi; i += pas) {
    p.push(-demi, 0, i, demi, 0, i, i, 0, -demi, i, 0, demi);
    for (let k = 0; k < 4; k++) n.push(0, 1, 0);
  }
  return { positions: new Float32Array(p), normales: new Float32Array(n),
           nb: p.length / 3, mode: 'LINES' };
}

/* --------------------------------------------------------------- nuanceurs */
const VERTEX = `#version 300 es
precision highp float;
in vec3 position;
in vec3 normale;
uniform mat4 uProjection, uVue, uModele;
uniform mat3 uNormale;
out vec3 vNormale;
out vec3 vMonde;
void main() {
  vec4 monde = uModele * vec4(position, 1.0);
  vMonde = monde.xyz;
  vNormale = normalize(uNormale * normale);
  gl_Position = uProjection * uVue * monde;
}`;

const FRAGMENT = `#version 300 es
precision highp float;
in vec3 vNormale;
in vec3 vMonde;
uniform vec3 uCouleur;
uniform float uEmission;
uniform float uOpacite;
uniform vec3 uCamera;
out vec4 sortie;
void main() {
  vec3 N = normalize(vNormale);
  vec3 L = normalize(vec3(0.45, 0.9, 0.35));
  vec3 V = normalize(uCamera - vMonde);
  vec3 H = normalize(L + V);

  float diffus = max(dot(N, L), 0.0);
  float speculaire = pow(max(dot(N, H), 0.0), 42.0) * 0.45;
  // Liseré lumineux sur les bords : donne du relief sans texture.
  float bord = pow(1.0 - max(dot(N, V), 0.0), 2.6);

  vec3 ambiant = uCouleur * 0.24;
  vec3 teinte = ambiant + uCouleur * diffus * 0.78
              + vec3(1.0) * speculaire
              + uCouleur * bord * 0.55
              + uCouleur * uEmission;
  sortie = vec4(teinte, uOpacite);
}`;

/* Version WebGL 1, utilisee si le telephone ne gere pas GLSL ES 3.0. */
const VERTEX_1 = VERTEX
  .replace('#version 300 es\n', '')
  .replace(/\bin\b/g, 'attribute').replace(/\bout\b/g, 'varying');
const FRAGMENT_1 = FRAGMENT
  .replace('#version 300 es\n', '')
  .replace(/\bin\b/g, 'varying')
  .replace('out vec4 sortie;', '')
  .replace(/sortie/g, 'gl_FragColor');

/* ------------------------------------------------------------------ scene */
class SceneUsine {
  constructor(canvas) {
    this.canvas = canvas;
    this.gl = canvas.getContext('webgl2', { antialias: true, alpha: true })
           || canvas.getContext('webgl', { antialias: true, alpha: true });
    this.actif = false;
    this.webgl2 = !!(this.gl && this.gl.drawBuffers);
    if (!this.gl) return;
    try {
      this._init();
      this.actif = true;
    } catch (erreur) {
      console.warn('Scene 3D indisponible :', erreur.message);
      this.actif = false;
    }
  }

  _compiler(type, source) {
    const gl = this.gl;
    const shader = gl.createShader(type);
    gl.shaderSource(shader, source);
    gl.compileShader(shader);
    if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
      throw new Error(gl.getShaderInfoLog(shader) || 'compilation refusee');
    }
    return shader;
  }

  _init() {
    const gl = this.gl;
    const [vs, fs] = this.webgl2 ? [VERTEX, FRAGMENT] : [VERTEX_1, FRAGMENT_1];
    const programme = gl.createProgram();
    gl.attachShader(programme, this._compiler(gl.VERTEX_SHADER, vs));
    gl.attachShader(programme, this._compiler(gl.FRAGMENT_SHADER, fs));
    gl.bindAttribLocation(programme, 0, 'position');
    gl.bindAttribLocation(programme, 1, 'normale');
    gl.linkProgram(programme);
    if (!gl.getProgramParameter(programme, gl.LINK_STATUS)) {
      throw new Error(gl.getProgramInfoLog(programme) || 'edition de liens refusee');
    }
    this.programme = programme;
    gl.useProgram(programme);

    this.u = {};
    for (const nom of ['uProjection', 'uVue', 'uModele', 'uNormale', 'uCouleur',
                       'uEmission', 'uOpacite', 'uCamera']) {
      this.u[nom] = gl.getUniformLocation(programme, nom);
    }

    this.maillages = {
      cube: this._televerser(geometrieCube()),
      sphere: this._televerser(geometrieSphere()),
      grille: this._televerser(geometrieGrille()),
    };

    gl.enable(gl.DEPTH_TEST);
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);

    /* Etat pilote par les evenements du serveur. */
    this.etat = {
      fournisseurs: [], actifs: new Set(), dalles: 0, objectif: 6,
      agent: null, pulsation: 0, particules: [],
    };
    this.angle = 0.6;
    this.hauteurCamera = 0.32;
    this.distance = 15;
    this.cible = 15;
    this._brancherGestes();
    this.dernier = performance.now();
  }

  _televerser(geometrie) {
    const gl = this.gl;
    const creer = (donnees) => {
      const tampon = gl.createBuffer();
      gl.bindBuffer(gl.ARRAY_BUFFER, tampon);
      gl.bufferData(gl.ARRAY_BUFFER, donnees, gl.STATIC_DRAW);
      return tampon;
    };
    return {
      positions: creer(geometrie.positions),
      normales: creer(geometrie.normales),
      nb: geometrie.nb,
      mode: geometrie.mode,
    };
  }

  _brancherGestes() {
    const canvas = this.canvas;
    let pointeur = null, ecartInitial = 0;

    const debut = (e) => {
      if (e.touches && e.touches.length === 2) {
        ecartInitial = Math.hypot(
          e.touches[0].clientX - e.touches[1].clientX,
          e.touches[0].clientY - e.touches[1].clientY) || 1;
        pointeur = null;
        return;
      }
      const p = e.touches ? e.touches[0] : e;
      pointeur = { x: p.clientX, y: p.clientY };
    };
    const bouger = (e) => {
      if (e.touches && e.touches.length === 2) {
        const ecart = Math.hypot(
          e.touches[0].clientX - e.touches[1].clientX,
          e.touches[0].clientY - e.touches[1].clientY) || 1;
        this.cible = Math.max(8, Math.min(30, this.cible * (ecartInitial / ecart)));
        ecartInitial = ecart;
        e.preventDefault();
        return;
      }
      if (!pointeur) return;
      const p = e.touches ? e.touches[0] : e;
      this.angle -= (p.clientX - pointeur.x) * 0.008;
      this.hauteurCamera = Math.max(-0.25, Math.min(0.95,
        this.hauteurCamera + (p.clientY - pointeur.y) * 0.004));
      pointeur = { x: p.clientX, y: p.clientY };
      e.preventDefault();
    };
    const fin = () => { pointeur = null; };

    canvas.addEventListener('mousedown', debut);
    window.addEventListener('mousemove', bouger);
    window.addEventListener('mouseup', fin);
    canvas.addEventListener('touchstart', debut, { passive: true });
    canvas.addEventListener('touchmove', bouger, { passive: false });
    canvas.addEventListener('touchend', fin);
    canvas.addEventListener('wheel', (e) => {
      this.cible = Math.max(8, Math.min(30, this.cible + e.deltaY * 0.012));
      e.preventDefault();
    }, { passive: false });
  }

  redimensionner() {
    const gl = this.gl;
    const ratio = Math.min(window.devicePixelRatio || 1, 2);
    const l = Math.floor(this.canvas.clientWidth * ratio);
    const h = Math.floor(this.canvas.clientHeight * ratio);
    if (this.canvas.width !== l || this.canvas.height !== h) {
      this.canvas.width = l; this.canvas.height = h;
      gl.viewport(0, 0, l, h);
    }
  }

  _dessiner(maillage, modele, couleur, emission = 0, opacite = 1) {
    const gl = this.gl;
    gl.bindBuffer(gl.ARRAY_BUFFER, maillage.positions);
    gl.enableVertexAttribArray(0);
    gl.vertexAttribPointer(0, 3, gl.FLOAT, false, 0, 0);
    gl.bindBuffer(gl.ARRAY_BUFFER, maillage.normales);
    gl.enableVertexAttribArray(1);
    gl.vertexAttribPointer(1, 3, gl.FLOAT, false, 0, 0);
    gl.uniformMatrix4fv(this.u.uModele, false, modele);
    gl.uniformMatrix3fv(this.u.uNormale, false, M4.normale(modele));
    gl.uniform3fv(this.u.uCouleur, couleur);
    gl.uniform1f(this.u.uEmission, emission);
    gl.uniform1f(this.u.uOpacite, opacite);
    gl.drawArrays(gl[maillage.mode], 0, maillage.nb);
  }

  majEtat(partiel) {
    Object.assign(this.etat, partiel);
  }

  pulser(agent) {
    this.etat.agent = agent;
    this.etat.pulsation = 1;
  }

  jeton(origine) {
    /* Une particule part de l'orbe du fournisseur vers la colonne centrale. */
    const index = Math.max(0, this.etat.fournisseurs.indexOf(origine));
    this.etat.particules.push({ depart: index, t: 0 });
    if (this.etat.particules.length > 70) this.etat.particules.shift();
  }

  /* La palette de la scene, lue sur la peau en cours.

     Les six couleurs etaient ecrites en dur, en bleu : la scene 3D restait
     cyan sous « ambre » et sous « console », au milieu d'une page entierement
     ambre ou verte. On croyait a une peau inachevee — c'etait une palette
     qui n'avait jamais su qu'il existait autre chose que « nuit » et
     « jour ». Elle se relit a chaque image : changer de peau la change.

     WebGL veut des triplets 0..1 ; les variables CSS sont en hexa ou en
     rgb(). La conversion evite une septieme liste de couleurs a tenir. */
  _palette() {
    const style = getComputedStyle(document.documentElement);
    const lire = (nom, secours) => {
      const v = String(style.getPropertyValue(nom) || '').trim();
      let c = null;
      if (v.startsWith('#')) {
        const h = v.length < 7
          ? v[1] + v[1] + v[2] + v[2] + v[3] + v[3] : v.slice(1, 7);
        c = [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16) / 255);
      } else {
        const m = v.match(/[\d.]+/g);
        if (m && m.length >= 3) c = m.slice(0, 3).map((x) => +x / 255);
      }
      return c && c.every((x) => x >= 0 && x <= 1) ? c : secours;
    };
    const fondu = (c, f) => c.map((x) => x * f);
    const accent = lire('--accent', [0.24, 0.55, 0.95]);
    const vert = lire('--vert', [0.30, 0.95, 0.62]);
    const doux = lire('--doux', [0.30, 0.40, 0.58]);
    return { grille: fondu(doux, 0.75), socle: fondu(doux, 0.34),
             dalle: accent, fantome: fondu(accent, 0.72),
             actif: vert, dormant: doux, anneau: accent,
             jeton: lire('--ambre', [1.0, 0.86, 0.42]) };
  }

  rendre(maintenant) {
    if (!this.actif) return;
    const gl = this.gl;
    const dt = Math.min(0.05, (maintenant - this.dernier) / 1000);
    this.dernier = maintenant;
    const temps = maintenant / 1000;

    this.redimensionner();
    this.distance += (this.cible - this.distance) * 0.08;
    this.etat.pulsation = Math.max(0, this.etat.pulsation - dt * 1.4);
    this.angle += dt * 0.09;

    gl.clearColor(0, 0, 0, 0);
    gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
    gl.useProgram(this.programme);

    const aspect = this.canvas.width / Math.max(this.canvas.height, 1);
    // Un ecran de telephone est etroit : a distance egale, les orbes en orbite
    // sortent du cadre. On recule proportionnellement au manque de largeur.
    const compensation = aspect < 1.35 ? Math.min(1.9, 1.35 / Math.max(aspect, 0.4)) : 1;
    const rayon = this.distance * compensation;
    const oeil = [
      Math.sin(this.angle) * rayon * Math.cos(this.hauteurCamera),
      2.0 + Math.max(this.etat.dalles, this.etat.objectif) * 0.2
          + Math.sin(this.hauteurCamera) * rayon * 0.8,
      Math.cos(this.angle) * rayon * Math.cos(this.hauteurCamera),
    ];
    gl.uniformMatrix4fv(this.u.uProjection, false,
      M4.perspective(Math.PI / 4.4, aspect, 0.1, 120));
    // La camera vise le milieu de la pile : sans cela, un produit long sort
    // par le haut et un produit court laisse le cadre a moitie vide.
    const hauteurPile = 0.32 + Math.max(this.etat.dalles, this.etat.objectif) * 0.42;
    const viseeY = Math.max(1.6, Math.min(9, hauteurPile * 0.55 + 1.1));
    gl.uniformMatrix4fv(this.u.uVue, false,
      M4.regarder(oeil, [0, viseeY, 0], [0, 1, 0]));
    gl.uniform3fv(this.u.uCamera, new Float32Array(oeil));

    /* Socle */
    const teintes = this._palette();
    this._dessiner(this.maillages.grille, M4.identite(), teintes.grille, 0.1, 0.5);
    this._dessiner(this.maillages.cube,
      M4.multiplier(M4.echelle(2.1, 0.16, 2.1), M4.translation(0, -0.1, 0)),
      teintes.socle, 0.02, 1);

    /* Colonne du produit : une dalle par section terminee */
    const dalles = Math.min(this.etat.dalles, 40);
    for (let i = 0; i < dalles; i++) {
      const y = 0.32 + i * 0.42;
      const apparition = Math.min(1, (temps * 2 - i * 0.12) % 1000);
      const oscillation = Math.sin(temps * 1.6 + i * 0.5) * 0.035;
      const modele = M4.multiplier(
        M4.multiplier(M4.echelle(1.5, 0.16, 1.05), M4.rotationY(i * 0.14 + oscillation)),
        M4.translation(0, y, 0));
      const chaud = i >= dalles - 1 ? 0.42 + this.etat.pulsation * 0.5 : 0.06;
      this._dessiner(this.maillages.cube, modele,
        teintes.dalle.map((c, k) => (k === 0 ? Math.min(1, c + i * 0.012) : c)),
        chaud, Math.min(1, apparition + 0.35));
    }

    /* Fantomes des sections restantes : une respiration lente les anime,
       pour que l'atelier au repos ne soit pas une image fixe. */
    for (let i = dalles; i < Math.min(this.etat.objectif, 40); i++) {
      const y = 0.32 + i * 0.42;
      const souffle = 0.5 + 0.5 * Math.sin(temps * 1.1 - i * 0.55);
      this._dessiner(this.maillages.cube,
        M4.multiplier(
          M4.multiplier(M4.echelle(1.42, 0.03, 1.0), M4.rotationY(temps * 0.12 + i * 0.3)),
          M4.translation(0, y + souffle * 0.05, 0)),
        teintes.fantome, souffle * 0.18, 0.12 + souffle * 0.16);
    }

    /* Orbes des fournisseurs */
    const liste = this.etat.fournisseurs;
    liste.forEach((nom, index) => {
      const a = temps * 0.22 + index * (Math.PI * 2 / Math.max(liste.length, 1));
      const r = 6.4;
      const actif = this.etat.actifs.has(nom);
      const y = 2.2 + Math.sin(temps * 0.8 + index) * 0.5;
      const taille = actif ? 0.46 + Math.sin(temps * 6) * 0.06 : 0.26;
      this._dessiner(this.maillages.sphere,
        M4.multiplier(M4.echelle(taille, taille, taille),
                      M4.translation(Math.sin(a) * r, y, Math.cos(a) * r)),
        actif ? teintes.actif : teintes.dormant,
        actif ? 0.85 : 0.05, actif ? 1 : 0.55);
      this._positions = this._positions || {};
      this._positions[index] = [Math.sin(a) * r, y, Math.cos(a) * r];
    });

    /* Particules : jetons qui remontent vers le produit */
    const restantes = [];
    for (const particule of this.etat.particules) {
      particule.t += dt * 0.75;
      if (particule.t >= 1) continue;
      restantes.push(particule);
      const depart = (this._positions || {})[particule.depart] || [0, 3, 0];
      const arrivee = [0, 0.5 + dalles * 0.42, 0];
      const t = particule.t;
      const courbe = Math.sin(t * Math.PI) * 1.5;
      const p = [
        depart[0] + (arrivee[0] - depart[0]) * t,
        depart[1] + (arrivee[1] - depart[1]) * t + courbe,
        depart[2] + (arrivee[2] - depart[2]) * t,
      ];
      const taille = 0.10 * (1 - t * 0.45);
      this._dessiner(this.maillages.sphere,
        M4.multiplier(M4.echelle(taille, taille, taille),
                      M4.translation(p[0], p[1], p[2])),
        teintes.jeton, 1.0, 1 - t * 0.5);
    }
    this.etat.particules = restantes;

    /* Anneau d'activite autour de la colonne */
    if (this.etat.pulsation > 0) {
      const r = 2.2 + (1 - this.etat.pulsation) * 3.2;
      const segments = 26;
      for (let i = 0; i < segments; i++) {
        const a = i * Math.PI * 2 / segments;
        this._dessiner(this.maillages.cube,
          M4.multiplier(M4.echelle(0.07, 0.07, 0.22),
                        M4.translation(Math.sin(a) * r, 0.45, Math.cos(a) * r)),
          teintes.anneau, 0.9, this.etat.pulsation * 0.8);
      }
    }
  }
}

window.SceneUsine = SceneUsine;
