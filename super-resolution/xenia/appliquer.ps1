# Construit l'arbre source de « Xenia + USR » sous Windows : clone
# xenia-canary-uwp au commit de reference, copie la bibliotheque USR dans
# third_party\usr et applique les 5 correctifs.
#
#   powershell -ExecutionPolicy Bypass -File xenia\appliquer.ps1 [dossier]
#
# Prerequis : Git pour Windows. Voir docs\XENIA.md.
param(
    [string]$Cible = (Join-Path (Get-Location) "xenia-usr"),
    [string]$Source = "https://github.com/amitamit99/xenia-canary-uwp.git",
    [string]$Commit = "3e236f08245f8f98b6813a6c249b6896dbfbd400"
)
$ErrorActionPreference = "Stop"
$Ici = Split-Path -Parent $MyInvocation.MyCommand.Path
$Usr = Split-Path -Parent $Ici

function Git-Ok {
    & git @args
    if ($LASTEXITCODE -ne 0) { throw "git $args : echec ($LASTEXITCODE)" }
}

if (Test-Path $Cible) { throw "Le dossier $Cible existe deja : choisir un autre dossier." }

Write-Host "== Xenia : $Source @ $($Commit.Substring(0, 7))"
Git-Ok clone --quiet $Source $Cible
Git-Ok -C $Cible -c advice.detachedHead=false checkout --quiet -b usr $Commit
Write-Host "== sous-modules de Xenia (quelques minutes)"
# comme « xb setup » : profondeur 1, sans xbyak_aarch64 (processeurs ARM)
$SousModules = (Select-String -CaseSensitive '(?<=path = )(?!third_party/xbyak_aarch64).+' `
                (Join-Path $Cible ".gitmodules")).Matches.Value
Git-Ok -C $Cible -c fetch.recurseSubmodules=on-demand submodule update --init --depth=1 `
       -j $env:NUMBER_OF_PROCESSORS @SousModules

Write-Host "== bibliotheque USR -> third_party\usr"
$Dest = Join-Path $Cible "third_party\usr"
New-Item -ItemType Directory -Force $Dest | Out-Null
foreach ($d in "include", "src", "shaders") {
    Copy-Item -Recurse -Force (Join-Path $Usr $d) $Dest
}
Copy-Item -Force (Join-Path $Ici "third_party_usr\CMakeLists.txt") $Dest
# licence MIT du depot : elle suit le code copie
Copy-Item -Force (Join-Path (Split-Path -Parent $Usr) "LICENSE") (Join-Path $Dest "LICENSE")

Write-Host "== correctifs"
$Patches = Get-ChildItem (Join-Path $Ici "patches\*.patch") | Sort-Object Name | ForEach-Object { $_.FullName }
Git-Ok -C $Cible -c user.name="Usine-IA" -c user.email="usr@usine-ia.local" -c core.autocrlf=false am --keep-cr --quiet @Patches
Git-Ok -C $Cible log --oneline -4

Write-Host ""
Write-Host "Arbre pret : $Cible (branche usr)."
Write-Host "Suite : cd $Cible ; cmake --preset vs ; puis ouvrir build\xenia.sln"
Write-Host "et compiler xenia-canary-uwp (Release | x64)."
Write-Host "Pas a pas, paquet et installation sur Xbox : super-resolution\docs\XENIA.md."
