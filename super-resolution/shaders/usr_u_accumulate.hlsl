// USR Universel, passe d'accumulation (resolution d'affichage).
//
//   1. voisinage 4x4 d'echantillons autour du pixel, a leurs positions
//      reelles (jitter ou non, pixel par pixel) : image fraiche (Lanczos-2,
//      sans rebond), residu interpole (tente), proximite du plus proche ;
//   2. historique reprojete (Catmull-Rom) et sa confiance ;
//   3. regles de base : reactivite = sortie de boite ou flot peu fiable,
//      gain = proximite / (confiance + proximite) ;
//   4. le reseau corrige ces deux decisions (logits) ;
//   5. nouveau = historique + gain * residu, ramene vers l'image fraiche
//      selon la reactivite.
// u0 : nouvel historique (YCoCg, confiance) ; u1 : diagnostic (reactivite,
// gain, confiance / max, confiance du flot).
// Jumeau NumPy : usr_ref/universel.py, UniversalUpscaler.dispatch().

#include "usr_u_common.hlsli"
#include "usr_network.hlsli"

Texture2D<float4>   t_Color    : register(t0); // image du jeu, [0, 1]
Texture2D<float2>   t_Motion   : register(t1); // mouvement final (px rendu)
Texture2D<float4>   t_Aux      : register(t2); // (confiance, jitter, fixe)
Texture2D<float4>   t_History  : register(t3); // historique precedent
Texture2D<float4>   t_Residual : register(t4); // (residu, sortie de boite)
RWTexture2D<float4> u_HistoryOut : register(u0);
RWTexture2D<float4> u_Debug      : register(u1);

[RootSignature(USR_U_ROOT_SIGNATURE)]
[numthreads(8, 8, 1)]
void main(uint3 id : SV_DispatchThreadID)
{
    const int2 dsize = int2(g_DisplaySize);
    const int2 rsize = int2(g_RenderSize);
    const int2 o = int2(id.xy);
    if (o.x >= dsize.x || o.y >= dsize.y)
        return;
    const bool first = (g_Flags & USR_U_FLAG_RESET) != 0;

    // --- 1. voisinage d'echantillons ---------------------------------------
    const float u = (float(o.x) + 0.5) / float(dsize.x);
    const float v = (float(o.y) + 0.5) / float(dsize.y);
    const float px = u * float(rsize.x) - 0.5;
    const float py = v * float(rsize.y) - 0.5;
    const int bx = int(floor(px - g_Jitter.x));
    const int by = int(floor(py - g_Jitter.y));

    float3 fr = 0.0, ur = 0.0;
    float fw = 0.0, uw = 0.0;
    float dmin = 1e9;
    float3 mn = USR_U_FLT_MAX, mx = -USR_U_FLT_MAX;
    float bmax = 0.0, cmax = 0.0;
    [unroll] for (int j = -1; j <= 2; ++j)
    {
        const int qy = clamp(by + j, 0, rsize.y - 1);
        [unroll] for (int i = -1; i <= 2; ++i)
        {
            const int qx = clamp(bx + i, 0, rsize.x - 1);
            const float4 aux = t_Aux.Load(int3(qx, qy, 0));
            const float jf = aux.g;
            const float dx = float(qx) + g_Jitter.x * jf - px;
            const float dy = float(qy) + g_Jitter.y * jf - py;
            const float wl = UsrULanczos2(dx) * UsrULanczos2(dy);
            const float3 c = UsrURgbToYCoCg(t_Color.Load(int3(qx, qy, 0)).rgb);
            fr = fr + c * wl;
            fw = fw + wl;
            const float wt = max(0.0, 1.0 - abs(dx)) * max(0.0, 1.0 - abs(dy));
            const float4 res = t_Residual.Load(int3(qx, qy, 0));
            ur = ur + res.xyz * wt;
            uw = uw + wt;
            dmin = min(dmin, dx * dx + dy * dy);
            if (i >= 0 && i <= 1 && j >= 0 && j <= 1)
            {
                mn = min(mn, c);
                mx = max(mx, c);
                bmax = max(bmax, res.w);
                cmax = max(cmax, aux.r);
            }
        }
    }
    const float3 fresh = clamp(fr / max(fw, 1e-6), mn, mx);
    const float3 upd = ur / max(uw, 1e-6);
    const float ratio = float(dsize.x) / float(rsize.x);
    const float w = exp(-dmin * ratio * ratio /
                        (2.0 * USR_U_SIGMA_PROX * USR_U_SIGMA_PROX));

    // --- 2. historique reprojete -------------------------------------------
    const int2 ri = clamp(int2(int(floor(u * float(rsize.x))),
                               int(floor(v * float(rsize.y)))),
                          int2(0, 0), rsize - 1);
    const float2 m = t_Motion.Load(int3(ri, 0));
    const float stat = t_Aux.Load(int3(ri, 0)).b;
    const float pu = u - m.x / float(rsize.x);
    const float pv = v - m.y / float(rsize.y);
    const bool valid = !first && UsrUInsideUv(float2(pu, pv));
    float3 hr = fresh;
    float nr = 0.0;
    if (!first)
    {
        hr = UsrUCatmullRom(t_History, float2(pu, pv), dsize);
        nr = UsrUBilinearAlpha(t_History, float2(pu, pv), dsize);
    }
    nr = valid ? nr : 0.0;

    // --- 3. regles de base --------------------------------------------------
    const float boxH = saturate(bmax / g_BoxT1);
    const float reactH = valid ? max(boxH, cmax) : 1.0;
    const float gainH = w / (nr + w);
    float react = reactH;
    float gain = gainH;

    // --- 4. reseau ------------------------------------------------------------
    if ((g_Flags & USR_U_FLAG_NETWORK) != 0 && g_NetStrength > 0.0)
    {
        const float rng = mx.x - mn.x;
        const float den = rng + USR_U_FEAT_EPS;
        float fx = pu * float(dsize.x) - 0.5;
        float fy = pv * float(dsize.y) - 0.5;
        fx = fx - floor(fx);
        fy = fy - floor(fy);
        float x[USR_NET_INPUTS];
        x[0] = boxH;
        x[1] = cmax;
        x[2] = min(abs(upd.x) / den, 8.0);
        x[3] = min(abs(fresh.x - hr.x) / den, 8.0);
        x[4] = min(4.0 * rng, 1.0);
        x[5] = nr / g_MaxCount;
        x[6] = w;
        x[7] = log2(1.0 + sqrt(m.x * m.x + m.y * m.y));
        x[8] = 4.0 * fx * (1.0 - fx) + 4.0 * fy * (1.0 - fy);
        x[9] = stat;
        const float2 net = UsrNetwork(x);
        react = UsrUSigmoid(UsrULogit(reactH) + g_NetStrength * net.x);
        gain = UsrUSigmoid(UsrULogit(gainH) + g_NetStrength * net.y);
        react = valid ? react : 1.0;
    }

    // --- 5. melange -------------------------------------------------------------
    const float3 acc = hr + gain * upd;
    const float3 outc = acc + (fresh - acc) * react;
    const float count = min(nr * (1.0 - react) + w, g_MaxCount);
    u_HistoryOut[o] = float4(outc, count);
    if ((g_Flags & USR_U_FLAG_DEBUG) != 0)
        u_Debug[o] = float4(react, gain, count / g_MaxCount, cmax);
}
