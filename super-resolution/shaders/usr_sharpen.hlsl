// Passe 3 (resolution d'affichage) : accentuation adaptative au contraste,
// puis retour en couleurs lineaires dans la texture de sortie du jeu.
//
// L'accentuation est plus forte dans les zones peu contrastees et
// s'efface pres des bords deja francs ; le resultat reste borne par le
// voisinage, donc pas de halo.
//
// Jumeau NumPy : usr_ref/core.py, fonction sharpen().

#include "usr_common.hlsli"

Texture2D<float4>   t_HistoryNew : register(t0);
RWTexture2D<float4> u_Output     : register(u0);

float3 LoadRgb(int2 p, int2 size)
{
    return t_HistoryNew.Load(int3(clamp(p, int2(0, 0), size - 1), 0)).rgb;
}

[RootSignature(USR_ROOT_SIGNATURE)]
[numthreads(8, 8, 1)]
void main(uint3 id : SV_DispatchThreadID)
{
    const int2 size = int2(g_DisplaySize);
    const int2 o = int2(id.xy);
    if (o.x >= size.x || o.y >= size.y)
        return;

    float3 c = LoadRgb(o, size);
    if (g_Sharpness > 0.0)
    {
        const float3 n = LoadRgb(o + int2(0, -1), size);
        const float3 s = LoadRgb(o + int2(0, 1), size);
        const float3 e = LoadRgb(o + int2(1, 0), size);
        const float3 w = LoadRgb(o + int2(-1, 0), size);
        const float3 mn = min(min(min(c, n), min(s, e)), w);
        const float3 mx = max(max(max(c, n), max(s, e)), w);
        const float3 amp = saturate(min(mn, 1.0 - mx) / max(mx, 1e-4));
        const float3 lobe = -USR_SHARPEN_PEAK * g_Sharpness * sqrt(amp);
        const float3 r = (c + lobe * (n + s + e + w)) / (1.0 + 4.0 * lobe);
        c = clamp(r, mn, mx);
    }
    u_Output[o] = float4(UsrUntonemap(c) / g_Exposure, 1.0);
}
