// USR Labo -- composition de l'image affichee :
//   * ecran partage : une vue a gauche de g_SplitX, une autre a droite ;
//   * vues de diagnostic (alpha, beta, confiance, desocclusion, mouvement) ;
//   * loupe (grossissement au plus proche voisin, pour voir les pixels) ;
//   * texte (menu, mesures) dessine avec une police bitmap.
// Sortie : image 8 bits deja compressee pour l'ecran, copiee dans la
// chaine d'echange (swap chain).

#include "labo_common.hlsli"

// Contenu d'une moitie d'ecran
#define LABO_VIEW_COLOR        0u  // texture couleur lineaire (t0 ou t1)
#define LABO_VIEW_ALPHA        1u  // canaux de la sortie diagnostic de USR
#define LABO_VIEW_BETA         2u
#define LABO_VIEW_CONFIDENCE   3u
#define LABO_VIEW_DISOCCLUSION 4u
#define LABO_VIEW_MOTION       5u  // vecteurs de mouvement du jeu

// Cellule de texte : glyphe (12 bits), couleur (4 bits), drapeaux.
#define LABO_CELL_GLYPH     0x00000FFFu
#define LABO_CELL_COLOR_SHIFT 12u
#define LABO_CELL_PANEL     0x00010000u  // fond sombre (panneau)
#define LABO_CELL_HIGHLIGHT 0x00020000u  // ligne selectionnee

// Ordre choisi pour qu'aucun vecteur ne chevauche une frontiere de 16
// octets : la structure C++ LaboComposeConstants est ainsi une simple
// copie champ a champ (18 valeurs 32 bits).
cbuffer LaboComposePass : register(b0)
{
    uint2  g_OutSize;
    uint2  g_TextGrid;     // colonnes, lignes
    uint2  g_CellSize;     // taille d'une cellule a l'ecran (pixels)
    uint2  g_GlyphSize;    // taille d'un glyphe dans la police (pixels)
    uint2  g_MotionSize;   // resolution de la texture de mouvement
    float2 g_ZoomCenter;   // pixels
    uint   g_SplitX;       // colonne de separation (>= largeur : pas de split)
    uint   g_LeftView;
    uint   g_RightView;
    float  g_ZoomFactor;   // 0 = pas de loupe
    float  g_ZoomRadius;   // pixels
    float  g_MotionScale;  // pixels de mouvement pour la saturation
};

Texture2D<float4>      t_Left   : register(t0);
Texture2D<float4>      t_Right  : register(t1);
Texture2D<float4>      t_Debug  : register(t2);
Texture2D<float2>      t_Motion : register(t3);
StructuredBuffer<uint> t_Font   : register(t4);
StructuredBuffer<uint> t_Text   : register(t5);

RWTexture2D<unorm float4> u_Out : register(u0);

static const float3 kPalette[8] = {
    float3(0.95, 0.95, 0.95),  // 0 blanc
    float3(0.60, 0.62, 0.68),  // 1 gris
    float3(1.00, 0.84, 0.25),  // 2 jaune
    float3(0.45, 0.85, 1.00),  // 3 cyan
    float3(0.45, 0.95, 0.50),  // 4 vert
    float3(1.00, 0.45, 0.40),  // 5 rouge
    float3(1.00, 0.62, 0.25),  // 6 orange
    float3(0.80, 0.55, 1.00),  // 7 violet
};

// Palette continue (bleu -> cyan -> vert -> jaune -> rouge) pour les
// grandeurs entre 0 et 1.
float3 Ramp(float s)
{
    s = saturate(s);
    const float3 c0 = float3(0.05, 0.05, 0.35);
    const float3 c1 = float3(0.00, 0.60, 0.90);
    const float3 c2 = float3(0.20, 0.85, 0.30);
    const float3 c3 = float3(0.98, 0.85, 0.15);
    const float3 c4 = float3(0.90, 0.15, 0.10);
    const float t = s * 4.0;
    if (t < 1.0) return lerp(c0, c1, t);
    if (t < 2.0) return lerp(c1, c2, t - 1.0);
    if (t < 3.0) return lerp(c2, c3, t - 2.0);
    return lerp(c3, c4, t - 3.0);
}

float3 Hsv(float h, float s, float v)
{
    const float3 k = saturate(abs(frac(h + float3(0.0, 2.0 / 3.0, 1.0 / 3.0))
                                  * 6.0 - 3.0) - 1.0);
    return v * lerp(1.0, k, s);
}

// Couleur affichee d'une vue au pixel p (deja compressee pour l'ecran).
float3 ViewPixel(uint view, bool left, int2 p)
{
    p = clamp(p, int2(0, 0), int2(g_OutSize) - 1);
    if (view == LABO_VIEW_COLOR)
    {
        const float3 c = left ? t_Left.Load(int3(p, 0)).rgb
                              : t_Right.Load(int3(p, 0)).rgb;
        return LaboDisplay(c);
    }
    if (view == LABO_VIEW_MOTION)
    {
        const int2 m = int2(float2(p) * float2(g_MotionSize) /
                            float2(g_OutSize));
        const float2 mv = t_Motion.Load(int3(
            clamp(m, int2(0, 0), int2(g_MotionSize) - 1), 0));
        const float len = length(mv);
        const float angle = atan2(mv.y, mv.x) / (2.0 * LABO_PI) + 0.5;
        return Hsv(angle, saturate(len / g_MotionScale),
                   0.25 + 0.75 * saturate(len / g_MotionScale));
    }
    const float4 d = t_Debug.Load(int3(p, 0));
    const float s = view == LABO_VIEW_ALPHA ? d.x
                  : view == LABO_VIEW_BETA ? d.y
                  : view == LABO_VIEW_CONFIDENCE ? d.z : d.w;
    // alpha est souvent minuscule : echelle racine pour le rendre lisible
    return Ramp(view == LABO_VIEW_ALPHA ? sqrt(s) : s);
}

float GlyphCoverage(uint glyph, uint2 local)
{
    const uint rowWords = (g_GlyphSize.x + 3u) / 4u;
    const uint index = (glyph * g_GlyphSize.y + local.y) * rowWords +
                       local.x / 4u;
    return float((t_Font[index] >> ((local.x & 3u) * 8u)) & 0xFFu) / 255.0;
}

[RootSignature(LABO_ROOT_SIGNATURE)]
[numthreads(8, 8, 1)]
void main(uint3 id : SV_DispatchThreadID)
{
    if (id.x >= g_OutSize.x || id.y >= g_OutSize.y)
        return;
    const int2 p = int2(id.xy);

    // --- image : ecran partage, loupe -----------------------------------
    int2 src = p;
    const float2 fromCenter = float2(p) + 0.5 - g_ZoomCenter;
    const float dist = length(fromCenter);
    const bool inLens = g_ZoomFactor > 0.0 && dist < g_ZoomRadius;
    if (inLens)
        src = int2(floor(g_ZoomCenter + fromCenter / g_ZoomFactor));
    const bool left = uint(max(src.x, 0)) < g_SplitX;
    float3 color = ViewPixel(left ? g_LeftView : g_RightView, left, src);

    if (inLens && dist > g_ZoomRadius - 3.0)
        color = float3(1.0, 0.84, 0.25);
    else if (!inLens && g_SplitX < g_OutSize.x &&
             abs(int(p.x) - int(g_SplitX)) <= 1)
        color = float3(1.0, 1.0, 1.0);

    // --- texte ------------------------------------------------------------
    const uint2 cell = id.xy / g_CellSize;
    if (cell.x < g_TextGrid.x && cell.y < g_TextGrid.y)
    {
        const uint v = t_Text[cell.y * g_TextGrid.x + cell.x];
        if ((v & LABO_CELL_PANEL) != 0)
            color *= 0.25;
        if ((v & LABO_CELL_HIGHLIGHT) != 0)
            color = lerp(color, float3(0.25, 0.32, 0.55), 0.85);
        const uint glyph = v & LABO_CELL_GLYPH;
        if (glyph != 0)
        {
            const uint2 local = (id.xy - cell * g_CellSize) * g_GlyphSize /
                                g_CellSize;
            const float cover = GlyphCoverage(glyph, local);
            const float3 ink = kPalette[(v >> LABO_CELL_COLOR_SHIFT) & 7u];
            color = lerp(color, ink, cover);
        }
    }

    u_Out[id.xy] = float4(color, 1.0);
}
