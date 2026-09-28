// USR Labo -- declarations communes aux passes du laboratoire (scene de
// test, verite terrain, agrandissements de comparaison, composition).
//
// Ces passes ne font PAS partie de l'upscaler : elles fabriquent ce qu'un
// jeu fournirait (couleur, profondeur, mouvement) et affichent le resultat.

#ifndef LABO_COMMON_HLSLI
#define LABO_COMMON_HLSLI

// Signature racine commune : 24 constantes par passe, la scene en CBV,
// 6 SRV et 3 UAV.
#define LABO_ROOT_SIGNATURE                             \
    "RootConstants(num32BitConstants=24, b0), "         \
    "CBV(b1), "                                         \
    "DescriptorTable(SRV(t0, numDescriptors=6)), "      \
    "DescriptorTable(UAV(u0, numDescriptors=3))"

static const float LABO_PI = 3.14159265358979;

// Modulo "a la Python" : resultat du signe du diviseur (fmod tronque).
float LaboMod(float x, float m)
{
    return x - m * floor(x / m);
}

// sin(2 pi x) avec reduction d'argument exacte : reste precis sur GPU
// meme quand x vaut des centaines de tours.
float LaboSinTurns(float x)
{
    return sin(2.0 * LABO_PI * (x - floor(x)));
}

// Meme compression que la reference Python (evaluate.to_srgb8).
float3 LaboDisplay(float3 c)
{
    c = max(c, 0.0);
    const float3 y = c / (1.0 + max(c.r, max(c.g, c.b)));
    return pow(saturate(y), 1.0 / 2.2);
}

#endif // LABO_COMMON_HLSLI
