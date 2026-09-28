// USR Universel, passe « residu » (resolution de rendu).
//
// L'historique (resolution d'affichage) predit, par Catmull-Rom, ce que
// chaque echantillon de l'image courante aurait du montrer ; on garde
// l'erreur (residu) et le test de boite : la prediction sort-elle de
// l'etendue des 9 echantillons voisins ? (signe d'un historique faux :
// zone decouverte, ecran anime, mouvement mal estime).
// u0 : (residu YCoCg, sortie de boite relative) en RGBA16F.
// Jumeau NumPy : usr_ref/universel.py, residual_pass().

#include "usr_u_common.hlsli"

Texture2D<float4>   t_Color   : register(t0); // image du jeu, [0, 1]
Texture2D<float2>   t_Motion  : register(t1); // mouvement final (px rendu)
Texture2D<float4>   t_Aux     : register(t2); // (confiance, jitter, fixe)
Texture2D<float4>   t_History : register(t3); // historique precedent
RWTexture2D<float4> u_Residual : register(u0);

[RootSignature(USR_U_ROOT_SIGNATURE)]
[numthreads(8, 8, 1)]
void main(uint3 id : SV_DispatchThreadID)
{
    const int2 rsize = int2(g_RenderSize);
    const int2 p = int2(id.xy);
    if (p.x >= rsize.x || p.y >= rsize.y)
        return;
    if ((g_Flags & USR_U_FLAG_RESET) != 0)
    {
        u_Residual[p] = float4(0.0, 0.0, 0.0, 0.0);
        return;
    }
    const float3 S = UsrURgbToYCoCg(t_Color.Load(int3(p, 0)).rgb);
    const float jf = t_Aux.Load(int3(p, 0)).g;
    const float2 m = t_Motion.Load(int3(p, 0));
    const float su = (float(p.x) + 0.5 + g_Jitter.x * jf) / float(rsize.x);
    const float sv = (float(p.y) + 0.5 + g_Jitter.y * jf) / float(rsize.y);
    const float2 puv = float2(su - m.x / float(rsize.x),
                              sv - m.y / float(rsize.y));
    const float3 pred = UsrUCatmullRom(t_History, puv, int2(g_DisplaySize));
    const float3 res = S - pred;

    float3 mn = USR_U_FLT_MAX, mx = -USR_U_FLT_MAX;
    [unroll] for (int dy = -1; dy <= 1; ++dy)
    {
        [unroll] for (int dx = -1; dx <= 1; ++dx)
        {
            const int2 q = clamp(p + int2(dx, dy), int2(0, 0), rsize - 1);
            const float3 c = UsrURgbToYCoCg(t_Color.Load(int3(q, 0)).rgb);
            mn = min(mn, c);
            mx = max(mx, c);
        }
    }
    const float3 o = max(max(mn - pred, pred - mx), 0.0);
    const float3 r = o / (mx - mn + USR_U_RANGE_EPS);
    float box = max(r.x, max(r.y, r.z));
    if (!UsrUInsideUv(puv))
        box = 1e3;
    u_Residual[p] = float4(res, box);
}
