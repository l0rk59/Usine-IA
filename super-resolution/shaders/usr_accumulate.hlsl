// Passe 2 (resolution d'affichage) : le coeur de l'upscaler.
//
//   1. reprojette l'historique a l'aide des vecteurs de mouvement ;
//   2. reconstruit l'image courante depuis les echantillons decales (jitter) ;
//   3. recadre l'historique dans la boite de couleurs du voisinage ;
//   4. le reseau decide combien croire l'image courante (alpha) et combien
//      garder l'historique brut plutot que recadre (beta) ;
//   5. melange et ecrit le nouvel historique (RGB compresse + confiance).
//
// Jumeau NumPy : usr_ref/core.py, fonctions accumulate() et features().

#include "usr_common.hlsli"
#include "usr_network.hlsli"

Texture2D<float4>   t_Color         : register(t0); // image rendue (lineaire)
Texture2D<float2>   t_DilatedMotion : register(t1);
Texture2D<float>    t_Disocclusion  : register(t2);
Texture2D<float4>   t_History       : register(t3); // historique precedent

RWTexture2D<float4> u_HistoryOut    : register(u0);

void CatmullRomWeights(float f, out float w[4])
{
    w[0] = f * (-0.5 + f * (1.0 - 0.5 * f));
    w[1] = 1.0 + f * f * (-2.5 + 1.5 * f);
    w[2] = f * (0.5 + f * (2.0 - 1.5 * f));
    w[3] = f * f * (-0.5 + 0.5 * f);
}

// Couleur en Catmull-Rom (16 lectures, net en mouvement), confiance en
// bilineaire (pas de rebond negatif sur un compteur).
void SampleHistory(float2 puv, int2 size, out float3 color, out float count)
{
    const float2 pp = puv * float2(size) - 0.5;
    const float2 i1 = floor(pp);
    const float2 f = pp - i1;
    const int2 base = int2(i1);

    float wx[4], wy[4];
    CatmullRomWeights(f.x, wx);
    CatmullRomWeights(f.y, wy);

    color = 0.0;
    [unroll] for (int j = 0; j < 4; ++j)
    {
        const int qy = clamp(base.y + j - 1, 0, size.y - 1);
        [unroll] for (int i = 0; i < 4; ++i)
        {
            const int qx = clamp(base.x + i - 1, 0, size.x - 1);
            color += t_History.Load(int3(qx, qy, 0)).rgb * (wx[i] * wy[j]);
        }
    }

    const int x0 = clamp(base.x, 0, size.x - 1);
    const int x1 = clamp(base.x + 1, 0, size.x - 1);
    const int y0 = clamp(base.y, 0, size.y - 1);
    const int y1 = clamp(base.y + 1, 0, size.y - 1);
    const float top = t_History.Load(int3(x0, y0, 0)).a * (1.0 - f.x) +
                      t_History.Load(int3(x1, y0, 0)).a * f.x;
    const float bot = t_History.Load(int3(x0, y1, 0)).a * (1.0 - f.x) +
                      t_History.Load(int3(x1, y1, 0)).a * f.x;
    count = top * (1.0 - f.y) + bot * f.y;
}

// Ramene h dans la boite le long du rayon vers son centre.
float3 ClipToBox(float3 h, float3 bmin, float3 bmax)
{
    const float3 center = 0.5 * (bmin + bmax);
    const float3 extent = 0.5 * (bmax - bmin) + 1e-5;
    const float3 offset = h - center;
    const float3 r = abs(offset) / extent;
    const float ratio = max(r.x, max(r.y, r.z));
    return ratio > 1.0 ? center + offset / ratio : h;
}

[RootSignature(USR_ROOT_SIGNATURE)]
[numthreads(8, 8, 1)]
void main(uint3 id : SV_DispatchThreadID)
{
    const int2 dsize = int2(g_DisplaySize);
    const int2 rsize = int2(g_RenderSize);
    const int2 o = int2(id.xy);
    if (o.x >= dsize.x || o.y >= dsize.y)
        return;

    // --- 1. reprojection -------------------------------------------------
    const float2 uv = (float2(o) + 0.5) / float2(dsize);
    const float2 rp = uv * float2(rsize);
    const int2 ri = clamp(int2(floor(rp)), int2(0, 0), rsize - 1);
    const float2 mv = t_DilatedMotion.Load(int3(ri, 0));
    const float dis = t_Disocclusion.Load(int3(ri, 0));
    const float2 puv = uv - mv;
    const bool valid = (g_Flags & USR_FLAG_RESET) == 0 && UsrInsideUv(puv);

    float3 hRaw = 0.0;
    float countPrev = 0.0;
    if (valid)
    {
        float count;
        SampleHistory(puv, dsize, hRaw, count);
        hRaw = max(hRaw, 0.0);
        countPrev = count * (1.0 - dis);
    }

    // --- 2. image courante -------------------------------------------------
    // Noyau large tant que l'historique manque, etroit ensuite (net).
    const float sigmaSharp = g_SigmaSharp;
    const float sigma = USR_SIGMA_FRESH + (sigmaSharp - USR_SIGMA_FRESH) *
                        saturate(countPrev / USR_KERNEL_COUNT);
    const float inv2s2 = 1.0 / (2.0 * sigma * sigma);
    const float inv2s2Sharp = 1.0 / (2.0 * sigmaSharp * sigmaSharp);

    const int2 ns = int2(floor(rp - g_Jitter));
    float sumW = 0.0;
    float cw = 0.0;
    float3 sumC = 0.0, m1 = 0.0, m2 = 0.0;
    float3 mn = USR_FLT_MAX, mx = -USR_FLT_MAX;
    [unroll] for (int dy = -1; dy <= 1; ++dy)
    {
        [unroll] for (int dx = -1; dx <= 1; ++dx)
        {
            const int2 q = clamp(ns + int2(dx, dy), int2(0, 0), rsize - 1);
            const float3 c = UsrRgbToYCoCg(UsrTonemap(
                t_Color.Load(int3(q, 0)).rgb * g_Exposure));
            const float2 d = float2(q) + 0.5 + g_Jitter - rp;
            const float d2 = d.x * d.x + d.y * d.y;
            const float w = exp(-d2 * inv2s2);
            cw += exp(-d2 * inv2s2Sharp);
            sumW += w;
            sumC += c * w;
            m1 += c;
            m2 += c * c;
            mn = min(mn, c);
            mx = max(mx, c);
        }
    }
    const float3 cur = sumC / max(sumW, 1e-6);
    const float3 mean = m1 / 9.0;
    const float3 stdv = sqrt(max(m2 / 9.0 - mean * mean, 0.0));

    // --- 3. recadrage --------------------------------------------------------
    const float3 hy = UsrRgbToYCoCg(hRaw);
    const float3 bmin = max(mean - g_ClipGamma * stdv, mn);
    const float3 bmax = min(mean + g_ClipGamma * stdv, mx);
    const float3 hClip = ClipToBox(hy, bmin, bmax);

    // --- 4. decision : heuristique, corrigee par le reseau --------------------
    const float alphaHeur = valid ? cw / (countPrev + cw) : 1.0;
    float alpha = alphaHeur;
    float3 hist = hClip;
    if (valid && (g_Flags & USR_FLAG_NETWORK) != 0)
    {
        const float sY = stdv.x + USR_EPS_SIGMA;
        const float sLen = length(stdv) + USR_EPS_SIGMA;
        const float2 mvPx = mv * float2(dsize);
        float2 fr = puv * float2(dsize) - 0.5;
        fr = fr - floor(fr);

        float x[USR_NET_INPUTS];
        x[0] = alphaHeur;
        x[1] = min(abs(hy.x - mean.x) / sY, 8.0);
        x[2] = min(length(hy - hClip) / sLen, 8.0);
        x[3] = min(stdv.x / (mean.x + 0.02), 4.0);
        x[4] = dis;
        x[5] = log2(1.0 + length(mvPx));
        x[6] = min(cw, 4.0);
        x[7] = countPrev / g_MaxCount;
        x[8] = min(abs(cur.x - mean.x) / sY, 8.0);
        x[9] = 4.0 * fr.x * (1.0 - fr.x) + 4.0 * fr.y * (1.0 - fr.y);

        const float2 net = UsrNetwork(x);
        const float a = clamp(alphaHeur, 1e-4, 1.0 - 1e-4);
        alpha = UsrSigmoid(log(a / (1.0 - a)) + net.x);
        hist = hClip + (hy - hClip) * UsrSigmoid(net.y);
    }

    // --- 5. melange ------------------------------------------------------------
    const float3 res = hist + (cur - hist) * alpha;
    const float newCount = valid
        ? min(min(countPrev + cw, cw / max(alpha, 1e-4)), g_MaxCount)
        : min(cw, g_MaxCount);
    u_HistoryOut[o] = float4(max(UsrYCoCgToRgb(res), 0.0), newCount);
}
