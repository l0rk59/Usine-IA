// USR Labo -- agrandissements de comparaison, sans aucune intelligence :
//   mode 0 : bilineaire (ce que fait un jeu qui se contente d'etirer) ;
//   mode 1 : plus proche voisin (montre l'image brute recue, pixels et
//            decalages du jitter compris).

#include "labo_common.hlsli"

cbuffer LaboUpscalePass : register(b0)
{
    uint2 g_SrcSize;
    uint2 g_DstSize;
    uint  g_Mode;
};

Texture2D<float4>   t_Source : register(t0);
RWTexture2D<float4> u_Dest   : register(u0);

float4 Load(int2 p)
{
    return t_Source.Load(int3(clamp(p, int2(0, 0), int2(g_SrcSize) - 1), 0));
}

[RootSignature(LABO_ROOT_SIGNATURE)]
[numthreads(8, 8, 1)]
void main(uint3 id : SV_DispatchThreadID)
{
    if (id.x >= g_DstSize.x || id.y >= g_DstSize.y)
        return;
    const float2 p = (float2(id.xy) + 0.5) / float2(g_DstSize) *
                     float2(g_SrcSize);
    float4 c;
    if (g_Mode == 1)
    {
        c = Load(int2(floor(p)));
    }
    else
    {
        const float2 q = p - 0.5;
        const int2 i = int2(floor(q));
        const float2 f = q - floor(q);
        c = lerp(lerp(Load(i), Load(i + int2(1, 0)), f.x),
                 lerp(Load(i + int2(0, 1)), Load(i + int2(1, 1)), f.x), f.y);
    }
    u_Dest[id.xy] = c;
}
