# Fiche technique de l'appareil

Relevee par `usine specs` le 2026-09-14T13:53:27Z.

Ce document repond a une question que `usine docteur` ne pose pas :
**qu'est-ce qui devrait etre dans `install.sh` pour que cet appareil
marche sans bricolage ?** Aucune cle API n'y figure.

## Ce qui manque

| Ce qui manque | Gravite | Pour l'avoir | Ce que son absence coute |
|---|---|---|---|
| ollama | optionnel | `apt install ollama` | pas de production hors ligne |

## L'appareil

| | |
|---|---|
| Systeme | Linux-6.18.44-fc-v32-x86_64-with-glibc2.39 |
| Architecture | x86_64 |
| Python | 3.11.15 (main, Mar  3 2026, 09:26:23) [GCC 13.3.0] |
| Termux | non |
| termux-api | absent |
| Memoire vive | 16073 Mo |
| Disque libre | 30072 Mo sur 258019 Mo |
| Dossier de travail | `/tmp/usine-fuite` |

## Outils

| Outil | Etat | Version | Si absent |
|---|---|---|---|
| `python3` | present | Python 3.11.15 | — |
| `git` | present | git version 2.43.0 | — |
| `node` | present | v22.22.2 | — |
| `termux-notification` | **absent** | — | aucune notification quand un produit sort, pendant que l'ecran est eteint |
| `termux-battery-status` | **absent** | — | l'usine continue ne peut pas s'arreter sur batterie faible |
| `termux-open` | **absent** | — | impossible d'ouvrir un PDF depuis le menu |
| `termux-share` | **absent** | — | impossible de partager une archive |
| `termux-wake-lock` | **absent** | — | Android suspend une fabrication longue quand l'ecran s'eteint |
| `ollama` | **absent** | — | pas de production hors ligne |
| `curl` | present | curl 8.5.0 (x86_64-pc-linux-gnu) libcurl/8.5.0 OpenSSL/3.0.13 zlib/1.3 brotli/1. | — |

## Fournisseurs configures

Nombre de cles seulement : aucune valeur n'est ecrite ici.

| Fournisseur | Variable | Cles | Genre |
|---|---|---|---|
| groq | `GROQ_API_KEY` | 1 | cle API |
| cerebras | `CEREBRAS_API_KEY` | 0 | cle API |
| gemini | `GEMINI_API_KEY` | 0 | cle API |
| mistral | `MISTRAL_API_KEY` | 0 | cle API |
| openrouter | `OPENROUTER_API_KEY` | 0 | cle API |
| github | `GITHUB_MODELS_TOKEN` | 0 | cle API |
| nvidia | `NVIDIA_API_KEY` | 0 | cle API |
| pollinations | `POLLINATIONS_TOKEN` | 0 | sans cle |
| ollama | `—` | 0 | local |
| llamacpp | `—` | 0 | local |

## Modules de la bibliotheque standard

L'usine n'utilise que la bibliotheque standard. Ces modules-la sont ceux dont elle ne peut pas se passer :

```
sqlite3, ssl, zlib, zipfile, urllib.request, hashlib, unicodedata, secrets, threading
```

Tous presents.
