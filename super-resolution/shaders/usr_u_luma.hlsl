// USR Universel, passe 1 (resolution de rendu) : luminance de l'image.
//
// u0 : luminance flottante (niveau 0 de la pyramide du flot) ;
// u1 : luminance entiere (tests d'egalite exacte : HUD, meme phase).
// Jumeau NumPy : usr_ref/flow.py, luma_int(), luma() et luma16().

#include "usr_u_common.hlsli"

Texture2D<float4>   t_Color  : register(t0); // image du jeu, [0, 1]
RWTexture2D<float>  u_Luma   : register(u0);
RWTexture2D<uint>   u_Luma16 : register(u1);

[RootSignature(USR_U_ROOT_SIGNATURE)]
[numthreads(8, 8, 1)]
void main(uint3 id : SV_DispatchThreadID)
{
    const int2 p = int2(id.xy);
    if (p.x >= int(g_RenderSize.x) || p.y >= int(g_RenderSize.y))
        return;
    // Canaux ramenes a 8 bits : luminance entiere R + 2 G + B (0..1020),
    // identique sur tous les GPU (independante de l'arrondi UNORM).
    precise const float3 k = floor(saturate(t_Color.Load(int3(p, 0)).rgb) *
                                   255.0 + 0.5);
    precise const float y = k.r + 2.0 * k.g + k.b;
    u_Luma[p] = y * (1.0 / 1020.0);
    u_Luma16[p] = uint(y);
}
