// USR Labo -- verite terrain : la scene rendue directement a la resolution
// d'affichage, avec N x N echantillons par pixel. C'est l'image que
// l'upscaler essaie de retrouver (et la reference des mesures en Python).

#include "labo_scene.hlsli"

cbuffer LaboTruthPass : register(b0)
{
    uint2 g_Size;      // resolution d'affichage
    uint  g_Samples;   // echantillons par axe (1 a 4)
};

RWTexture2D<float4> u_Truth : register(u0);

[RootSignature(LABO_ROOT_SIGNATURE)]
[numthreads(8, 8, 1)]
void main(uint3 id : SV_DispatchThreadID)
{
    if (id.x >= g_Size.x || id.y >= g_Size.y)
        return;
    const uint n = clamp(g_Samples, 1u, 4u);
    float3 acc = 0.0;
    for (uint j = 0; j < n; ++j)
    {
        for (uint i = 0; i < n; ++i)
        {
            const float2 offset = (float2(i, j) + 0.5) / float(n);
            float3 color;
            float invz;
            float2 motion;
            LaboShade((float2(id.xy) + offset) / float2(g_Size), color, invz,
                      motion);
            acc += color;
        }
    }
    u_Truth[id.xy] = float4(acc / float(n * n), 1.0);
}
