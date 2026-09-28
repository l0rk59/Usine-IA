// USR Universel, derniere passe (resolution d'affichage) : retour en RGB,
// borne a [0, 1], accentuation RCAS optionnelle (celle de FSR 1).
// Jumeau NumPy : usr_ref/universel.py, output_pass() et rcas().

#include "usr_u_common.hlsli"

Texture2D<float4>   t_History : register(t0); // historique de cette image
RWTexture2D<float4> u_Output  : register(u0);

float3 LoadRgb(int2 q, int2 size)
{
    q = clamp(q, int2(0, 0), size - 1);
    return saturate(UsrUYCoCgToRgb(t_History.Load(int3(q, 0)).rgb));
}

[RootSignature(USR_U_ROOT_SIGNATURE)]
[numthreads(8, 8, 1)]
void main(uint3 id : SV_DispatchThreadID)
{
    const int2 size = int2(g_DisplaySize);
    const int2 p = int2(id.xy);
    if (p.x >= size.x || p.y >= size.y)
        return;
    float3 e = LoadRgb(p, size);
    if (g_Sharpness > 0.0)
    {
        const float3 b = LoadRgb(p + int2(0, -1), size);
        const float3 d = LoadRgb(p + int2(-1, 0), size);
        const float3 f = LoadRgb(p + int2(1, 0), size);
        const float3 h = LoadRgb(p + int2(0, 1), size);
        const float3 mn4 = min(min(b, d), min(f, h));
        const float3 mx4 = max(max(b, d), max(f, h));
        const float3 hitMin = mn4 / max(4.0 * mx4, 1e-6);
        const float3 hitMax = (1.0 - mx4) / min(4.0 * mn4 - 4.0, -1e-6);
        const float3 lobeRgb = max(-hitMin, hitMax);
        const float lobe = clamp(max(lobeRgb.r, max(lobeRgb.g, lobeRgb.b)),
                                 -0.1875, 0.0) * g_Sharpness;
        e = saturate((lobe * (b + d + f + h) + e) / (4.0 * lobe + 1.0));
    }
    u_Output[p] = float4(e, 1.0);
}
