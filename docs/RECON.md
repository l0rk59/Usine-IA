# Recon & sécurité

Un outil de reconnaissance et d'audit de surface, pour la **divulgation
responsable** — trouver ce qui cloche sur un domaine et le signaler
proprement à son propriétaire.

Ce n'est pas un scanner d'attaque, et ce n'est pas de la timidité : scanner
un bien d'autrui avec des charges d'attaque (injection, brute-force,
exploitation) est illégal en France sans son accord écrit, *quelle que soit
l'intention*, et un tel outil ferait tomber celui qui s'en sert. Cet outil
reste du bon côté de cette ligne — et c'est justement là qu'on trouve
beaucoup de failles réelles que peu de gens signalent.

## Deux modes, et la différence est la ligne légale

| | Ce qu'il fait | Autorisation |
|---|---|---|
| **Passif** (défaut) | crt.sh, DNS-sur-HTTPS, RDAP | aucune — que du public |
| **Surface** | une requête HTTPS vers le domaine | affirmée par l'opérateur |

Le passif ne touche jamais la cible : il lit des registres publics. La
[reconnaissance passive est « presque universellement permise »](https://reconshield.in/blog/anatomy-of-passive-osint)
précisément parce qu'on ne lit que des données publiques. La surface, elle,
contacte le domaine — une seule requête, ce qu'un navigateur fait en ouvrant
une page — et n'a de sens que pour un domaine dont on a la charge, ou couvert
par un programme de bug bounty. Cette affirmation est un **acte de
l'opérateur** : ni le menu, ni le tableau de bord, ni le serveur ne
l'activent à sa place.

## Ce qu'il trouve, et pourquoi c'est signalable

- **E-mail usurpable** — pas de DMARC, ou `p=none` : n'importe qui peut
  écrire au nom du domaine. La faille la plus courante et la plus facile à
  corriger. SPF trop permissif est signalé aussi.
- **En-têtes de sécurité absents** — HSTS (grave), CSP, X-Content-Type-Options,
  X-Frame-Options, Referrer-Policy.
- **Dépôt `.git` exposé** — `/.git/HEAD` servi : le code source se reconstitue.
  Un seul GET d'un chemin précis, lu, jamais exploité.
- **TLS obsolète**, cookie sans `Secure`, version du serveur exposée.
- **Pas de `security.txt`** — rien n'indique comment signaler
  ([RFC 9116](https://www.rfc-editor.org/info/rfc9116/)) : c'est la première
  chose à recommander.
- **Surface d'attaque** — les sous-domaines vus dans les journaux de
  transparence des certificats.

Chaque constat porte une gravité, et l'ensemble donne un **score de posture
sur 100** — grossier à dessein : il ordonne, il ne juge pas.

## Le signalement, prêt à envoyer

`--rapport` (ou la case dans le menu / le tableau de bord) rédige un
courrier de divulgation à partir des constats : classé par priorité, adressé
au contact trouvé dans `security.txt`, factuel et courtois. Il décrit **ce
qu'il faut corriger, jamais comment exploiter**, et rappelle de laisser au
propriétaire un délai raisonnable. On le relit avant d'envoyer.

## Depuis les trois interfaces

```bash
usine recon mon-site.fr                    # passif : registres publics
usine recon mon-site.fr --autorise         # + surface (domaine sous votre charge)
usine recon mon-site.fr --autorise --rapport --chercheur "Votre Nom"
```

Menu Termux → **Recon & sécurité**, qui pose la porte d'autorisation en
clair. Tableau de bord → carte **Recon & sécurité**, avec la case à cocher
et l'affichage des constats par gravité.

## Ce qu'il ne fait pas, et ne fera pas

Envoyer une charge d'attaque, forcer un mot de passe, balayer des ports en
masse, exploiter une faille, contourner une protection. Ces actions sont
hors de portée de l'outil par conception, pas par oubli.
