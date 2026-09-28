// USR Labo -- rendu de la scene en resolution de rendu : exactement ce
// qu'un moteur de jeu donnerait a USR (un echantillon par pixel, decale par
// le jitter, plus profondeur et vecteurs de mouvement).

#include "labo_scene.hlsli"

cbuffer LaboScenePass : register(b0)
{
    uint2  g_Size;       // resolution de rendu
    float2 g_Jitter;     // position de l'echantillon dans le pixel
};

// Formats choisis comme dans un vrai moteur : couleur HDR 16 bits,
// profondeur "reversed-Z infinie" (proche = 1, near = 1 : d = 1/z), et
// vecteurs de mouvement en pixels (courant - precedent).
RWTexture2D<float4> u_Color  : register(u0);
RWTexture2D<float>  u_Depth  : register(u1);
RWTexture2D<float2> u_Motion : register(u2);

[RootSignature(LABO_ROOT_SIGNATURE)]
[numthreads(8, 8, 1)]
void main(uint3 id : SV_DispatchThreadID)
{
    if (id.x >= g_Size.x || id.y >= g_Size.y)
        return;
    const float2 uv = (float2(id.xy) + 0.5 + g_Jitter) / float2(g_Size);
    float3 color;
    float invz;
    float2 motion;
    LaboShade(uv, color, invz, motion);
    u_Color[id.xy] = float4(color, 1.0);
    u_Depth[id.xy] = invz;
    u_Motion[id.xy] = motion * float2(g_Size);
}
