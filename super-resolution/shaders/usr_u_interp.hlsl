// USR Universel, generation d'images, passe 2 (resolution d'affichage) :
// l'image a l'instant g_Time entre la sortie precedente et la courante.
// Jumeau NumPy : usr_ref/interpolation.py, interpoler() ; le pourquoi de
// chaque etape y est explique.

#include "usr_u_interp.hlsli"

RWTexture2D<float4> u_Output : register(u0);

// Ecart du flot a ses 8 voisins et, si USR_U_FLAG_PREV, au flot precedent
// lu la ou le point etait (pixels de rendu) : doute_du_flot().
float DouteDuFlot(int2 q)
{
    const int2 rs = int2(g_RenderSize);
    const float2 m = t_Motion.Load(int3(q, 0));
    float d = 0.0;
    [unroll] for (int j = -1; j <= 1; ++j)
    {
        [unroll] for (int i = -1; i <= 1; ++i)
        {
            const int2 n = clamp(q + int2(i, j), int2(0, 0), rs - 1);
            const float2 e = abs(t_Motion.Load(int3(n, 0)) - m);
            d = max(d, max(e.x, e.y));
        }
    }
    if ((g_Flags & USR_U_FLAG_PREV) != 0)
    {
        const float2 uvp = (float2(q) + 0.5 - m) / float2(g_RenderSize);
        const float2 e = abs(
            t_MotionPrev.Load(int3(UsrUNearestIndex(uvp, rs), 0)) - m);
        d = max(d, max(e.x, e.y));
    }
    return d;
}

float Exp2Accord(float e)
{
    const float x = e / USR_U_SIGMA_ACCORD;
    return exp(-(x * x));
}

[RootSignature(USR_U_ROOT_SIGNATURE)]
[numthreads(8, 8, 1)]
void main(uint3 id : SV_DispatchThreadID)
{
    const int2 ds = int2(g_DisplaySize);
    const int2 p = int2(id.xy);
    if (p.x >= ds.x || p.y >= ds.y)
        return;
    const float t = g_Time;
    float2 uv, uvc0, m1;
    UsrUInterpMotion(p, uv, uvc0, m1);
    const int2 q = UsrUNearestIndex(uvc0, int2(g_RenderSize));
    const float doute = saturate((DouteDuFlot(q) - USR_U_SEUIL_FLOT) /
                                 USR_U_SEUIL_FLOT);

    const UsrUHypothese h1 = UsrUInterpHypothese(uv, m1);
    const UsrUHypothese h0 = UsrUInterpHypothese(uv, float2(0.0, 0.0));
    float2 somme = 0.0;
    [unroll] for (int j = -1; j <= 1; ++j)
    {
        [unroll] for (int i = -1; i <= 1; ++i)
        {
            const int2 n = clamp(p + int2(i, j), int2(0, 0), ds - 1);
            somme += t_Ecart.Load(int3(n, 0));
        }
    }
    const float e1 = h1.dedans ? somme.x / 9.0 : 1.0;
    const float e0 = somme.y / 9.0;
    const float w1 = Exp2Accord(e1) * (1.0 - doute);
    const float w0 = USR_U_POIDS_SUR_PLACE * Exp2Accord(e0);
    const float a = w1 / (w1 + w0 + 1e-6);
    const float3 fondu = h0.cp + (h0.cc - h0.cp) * t;
    const float3 suivi = h1.cp + (h1.cc - h1.cp) * t;
    const float3 melange = fondu + (suivi - fondu) * a;

    const bool douteux = doute > 0.5;
    const float meilleur = douteux ? e0 : min(e1, e0);
    const float repli = saturate((meilleur - USR_U_SIGMA_ACCORD) /
                                 USR_U_SIGMA_ACCORD);
    const float3 seule = douteux ? fondu : h1.cc;
    u_Output[p] = float4(saturate(melange + (seule - melange) * repli), 1.0);
}
