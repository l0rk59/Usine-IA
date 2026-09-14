# Fiche technique de l'appareil

Relevee par `usine specs` le 2026-09-14T12:31:30Z.

Ce document repond a une question que `usine docteur` ne pose pas :
**qu'est-ce qui devrait etre dans `install.sh` pour que cet appareil
marche sans bricolage ?** Aucune cle API n'y figure.

## Ce qui manque

| Ce qui manque | Gravite | Pour l'avoir | Ce que son absence coute |
|---|---|---|---|
| une cle API | bloquant | `usine cles` | sans cle, seul le quota anonyme partage est disponible et il ne suffit pas a un produit entier |

## L'appareil

| | |
|---|---|
| Systeme | Android-17-aarch64-64bit |
| Architecture | aarch64 |
| Python | 3.14.6 (main, Jul  5 2026, 10:35:55) [Clang 21.0.0 (https://android.googlesource.com/toolchain/llvm-project 5e96669f0 |
| Termux | oui |
| termux-api | present |
| Memoire vive | 11276 Mo |
| Disque libre | 787375 Mo sur 995134 Mo |
| Dossier de travail | `/data/data/com.termux/files/home/Usine-IA/atelier` |

## Outils

| Outil | Etat | Version | Si absent |
|---|---|---|---|
| `python3` | present | Python 3.14.6 | — |
| `git` | present | git version 2.55.0 | — |
| `node` | present | v24.18.0 | — |
| `termux-notification` | present | getopt: unrecognized option `--version' | — |
| `termux-battery-status` | present | termux-battery-status: illegal option -- | — |
| `termux-open` | present | getopt: unrecognized option `--version' | — |
| `termux-share` | present | termux-share: illegal option -- | — |
| `termux-wake-lock` | present | usage: termux-wake-lock | — |
| `ollama` | present | ollama version is 0.31.1 | — |
| `curl` | present | curl 8.22.0 (aarch64-unknown-linux-android) libcurl/8.22.0 OpenSSL/3.6.3 zlib/1. | — |

## Fournisseurs configures

Nombre de cles seulement : aucune valeur n'est ecrite ici.

| Fournisseur | Variable | Cles | Genre |
|---|---|---|---|
| groq | `GROQ_API_KEY` | 0 | cle API |
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
