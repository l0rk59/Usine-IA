// USR Labo -- la scene de test, portee de usr_ref/scene.py.
//
// Meme decor que celui qui a servi a entrainer et mesurer USR : fond qui
// defile, rayures et lignes plus fines qu'un pixel, points HDR, ecran anime
// et neon sans vecteurs de mouvement, objets qui se croisent. Les positions
// (camera, centres des objets, a l'image courante et a la precedente) sont
// calculees par le CPU en double precision et passees dans LaboScene.

#ifndef LABO_SCENE_HLSLI
#define LABO_SCENE_HLSLI

#include "labo_common.hlsli"

static const float LABO_BACKGROUND_DEPTH = 20.0;
static const uint LABO_MAX_OBJECTS = 8;

struct LaboObject
{
    float4 centers;  // xy = centre a l'image courante, zw = precedente (uv)
    float4 shape;    // x = rayon, y = profondeur, z = anneaux, w = 0 disque / 1 boite
    float4 tint;     // rgb
};

cbuffer LaboScene : register(b1)
{
    float4 g_Camera;       // xy = camera courante, zw = precedente (monde)
    float  g_Aspect;
    float  g_ScreenPhase;  // defilement de l'ecran anime, en tours
    uint   g_NeonOn;
    uint   g_ObjectCount;  // objets tries du plus loin au plus proche
    LaboObject g_Objects[LABO_MAX_OBJECTS];
};

float3 LaboBackground(float wx, float wy)
{
    const float3 base = float3(0.35 + 0.15 * sin(1.3 * wx),
                               0.30 + 0.12 * sin(1.1 * wy + 1.0),
                               0.40 + 0.15 * cos(0.7 * (wx + wy)));
    const float checker =
        LaboMod(floor(wx / 0.1) + floor(wy / 0.1), 2.0) * 0.25 + 0.75;
    float3 col = base * checker;

    // rayures fines, une bande sur trois
    if (LaboMod(floor(wy / 0.3), 3.0) == 0.0)
        col *= 0.35 + 0.65 * (0.5 + 0.5 * LaboSinTurns(wx / 0.025));

    // grille de lignes plus fines qu'un pixel de rendu
    const float gx = abs(wx / 0.22 - round(wx / 0.22)) * 0.22;
    const float gy = abs(wy / 0.18 - round(wy / 0.18)) * 0.18;
    if (gx < 0.002 || gy < 0.002)
        col = float3(0.95, 0.9, 0.7);

    // points HDR
    const float cx = round(wx / 0.37) * 0.37;
    const float cy = round(wy / 0.29) * 0.29;
    if ((wx - cx) * (wx - cx) + (wy - cy) * (wy - cy) < 0.006 * 0.006)
        col = float3(6.0, 5.0, 3.5);
    return col;
}

// Ecran qui defile et neon qui clignote : ils changent SANS vecteur de
// mouvement, comme l'eau, les particules ou les ecrans d'un vrai jeu.
float3 LaboAnimated(float3 col, float wx, float wy)
{
    const float px = LaboMod(wx, 1.7);
    const float py = LaboMod(wy, 1.3);
    if (px > 0.9 && px < 1.45 && py > 0.25 && py < 0.6)
    {
        const float scroll =
            0.5 + 0.5 * LaboSinTurns(px * 7.0 + py * 2.0 - g_ScreenPhase);
        col = float3(0.2 + 0.8 * scroll, 0.9 * scroll * scroll,
                     1.0 - 0.7 * scroll);
    }
    if (px > 0.2 && px < 0.7 && abs(py - 0.95) < 0.012)
        col = g_NeonOn != 0 ? float3(3.0, 0.4, 2.2) : float3(0.25, 0.05, 0.2);
    return col;
}

float3 LaboObjectColor(LaboObject o, float lx, float ly)
{
    float pattern;
    if (o.shape.w < 0.5)
        pattern = 0.55 + 0.45 * sin(o.shape.z * sqrt(lx * lx + ly * ly));
    else
        pattern = 0.6 + 0.4 * LaboMod(floor((lx + ly) * 9.0), 2.0);
    return o.tint.rgb * pattern;
}

// Ce que verrait un rayon en uv : couleur, 1 / profondeur, mouvement (uv,
// courant - precedent).
void LaboShade(float2 uv, out float3 color, out float invz, out float2 motion)
{
    const float wx = uv.x * g_Aspect + g_Camera.x;
    const float wy = uv.y + g_Camera.y;
    color = LaboAnimated(LaboBackground(wx, wy), wx, wy);
    float depth = LABO_BACKGROUND_DEPTH;
    motion = float2(-(g_Camera.x - g_Camera.z) / g_Aspect,
                    -(g_Camera.y - g_Camera.w));

    for (uint k = 0; k < g_ObjectCount && k < LABO_MAX_OBJECTS; ++k)
    {
        const LaboObject o = g_Objects[k];
        const float lx = (uv.x - o.centers.x) * g_Aspect / o.shape.x;
        const float ly = (uv.y - o.centers.y) / o.shape.x;
        const bool inside = o.shape.w < 0.5
            ? lx * lx + ly * ly < 1.0
            : abs(lx) < 1.0 && abs(ly) < 0.7;
        if (inside && o.shape.y < depth)
        {
            color = LaboObjectColor(o, lx, ly);
            depth = o.shape.y;
            motion = o.centers.xy - o.centers.zw;
        }
    }
    invz = 1.0 / depth;
}

#endif // LABO_SCENE_HLSLI
