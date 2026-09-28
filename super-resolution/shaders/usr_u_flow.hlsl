// USR Universel : estimation du mouvement a un niveau de la pyramide.
//
// Pour chaque pixel : essai d'une liste fixe de candidats (mouvement de
// SCENE m, en pixels du niveau), cout = SAD 5x5 entre l'image courante et
// la precedente lue en p + f, f = dJ - m (jitter compense), plus une
// penalite d'ecart au mouvement attendu ; puis une iteration de
// Lucas-Kanade. Ecrit le mouvement brut (la mediane vient ensuite).
// Jumeau NumPy : usr_ref/flow.py, FlowEstimator.__call__ (boucle des
// niveaux), select(), lucas_kanade().

#include "usr_u_common.hlsli"

Texture2D<float>    t_Cur      : register(t0); // luminance courante (niveau)
Texture2D<float>    t_Prev     : register(t1); // luminance precedente
Texture2D<float2>   t_PrevGrad : register(t2); // gradient de t_Prev
Texture2D<float2>   t_Parent   : register(t3); // mouvement du niveau parent
Texture2D<float2>   t_Temporal : register(t4); // mouvement final precedent
RWTexture2D<float2> u_Motion   : register(u0);

static int2 s_Size;

float LoadCur(int2 p)
{
    return t_Cur.Load(int3(clamp(p, int2(0, 0), s_Size - 1), 0));
}

// Bilineaire ecrit a la main (meme precision sur tous les GPU).
float BilinearPrev(precise float x, precise float y)
{
    x = clamp(x, 0.0, float(s_Size.x - 1));
    y = clamp(y, 0.0, float(s_Size.y - 1));
    precise const float x0 = floor(x);
    precise const float y0 = floor(y);
    precise const float ax = x - x0;
    precise const float ay = y - y0;
    const int ix0 = int(x0);
    const int iy0 = int(y0);
    const int ix1 = min(ix0 + 1, s_Size.x - 1);
    const int iy1 = min(iy0 + 1, s_Size.y - 1);
    precise const float a00 = t_Prev.Load(int3(ix0, iy0, 0));
    precise const float a01 = t_Prev.Load(int3(ix1, iy0, 0));
    precise const float a10 = t_Prev.Load(int3(ix0, iy1, 0));
    precise const float a11 = t_Prev.Load(int3(ix1, iy1, 0));
    precise const float top = a00 + (a01 - a00) * ax;
    precise const float bot = a10 + (a11 - a10) * ax;
    precise const float r = top + (bot - top) * ay;
    return r;
}

float2 BilinearGrad(precise float x, precise float y)
{
    x = clamp(x, 0.0, float(s_Size.x - 1));
    y = clamp(y, 0.0, float(s_Size.y - 1));
    precise const float x0 = floor(x);
    precise const float y0 = floor(y);
    precise const float ax = x - x0;
    precise const float ay = y - y0;
    const int ix0 = int(x0);
    const int iy0 = int(y0);
    const int ix1 = min(ix0 + 1, s_Size.x - 1);
    const int iy1 = min(iy0 + 1, s_Size.y - 1);
    precise const float2 a00 = t_PrevGrad.Load(int3(ix0, iy0, 0));
    precise const float2 a01 = t_PrevGrad.Load(int3(ix1, iy0, 0));
    precise const float2 a10 = t_PrevGrad.Load(int3(ix0, iy1, 0));
    precise const float2 a11 = t_PrevGrad.Load(int3(ix1, iy1, 0));
    precise const float2 top = a00 + (a01 - a00) * ax;
    precise const float2 bot = a10 + (a11 - a10) * ax;
    precise const float2 r = top + (bot - top) * ay;
    return r;
}

float PatchSad(int2 p, float2 f)
{
    precise float acc = 0.0;
    [unroll] for (int oy = -USR_U_PATCH_R; oy <= USR_U_PATCH_R; ++oy)
    {
        [unroll] for (int ox = -USR_U_PATCH_R; ox <= USR_U_PATCH_R; ++ox)
        {
            precise const float c = LoadCur(p + int2(ox, oy));
            precise const float q = BilinearPrev(float(p.x) + float(ox) + f.x,
                                         float(p.y) + float(oy) + f.y);
            acc = acc + abs(c - q);
        }
    }
    return acc;
}

float Contrast(int2 p)
{
    precise float taps[25];
    precise float total = 0.0;
    [unroll] for (int k = 0; k < 25; ++k)
    {
        taps[k] = LoadCur(p + int2(k % 5 - 2, k / 5 - 2));
        total = total + taps[k];
    }
    precise const float mean = total * (1.0 / 25.0);
    precise float acc = 0.0;
    [unroll] for (int k2 = 0; k2 < 25; ++k2)
        acc = acc + abs(taps[k2] - mean);
    return acc;
}

float2 ParentMotion(int2 p, int2 d)
{
    const int2 q = clamp(p / 2 + d, int2(0, 0), int2(g_ParentSize) - 1);
    return 2.0 * t_Parent.Load(int3(q, 0));
}

// Candidat : garde le meilleur (strictement moins cher ; le premier gagne
// les egalites, comme la reference).
void Try(int2 p, float2 m, float2 prior, float2 j, float weight,
         inout float best, inout float2 bestM, inout bool any)
{
    precise const float raw = PatchSad(p, j - m) +
                              weight * (abs(m.x - prior.x) + abs(m.y - prior.y));
    // comparaison a resolution fixe (voir flow.quantize_cost)
    precise const float cost = floor(raw * USR_U_COST_SCALE + 0.5);
    if (!any || cost < best)
    {
        best = cost;
        bestM = m;
        any = true;
    }
}

[RootSignature(USR_U_ROOT_SIGNATURE)]
[numthreads(8, 8, 1)]
void main(uint3 id : SV_DispatchThreadID)
{
    s_Size = int2(g_LevelSize);
    const int2 p = int2(id.xy);
    if (p.x >= s_Size.x || p.y >= s_Size.y)
        return;

    const uint level = g_Level;
    precise const float s = 1.0 / float(1u << level);
    precise const float2 j = g_JitterDelta * s;
    precise const float weight = USR_U_LAMBDA *
                         (Contrast(p) + 25.0 * USR_U_CONTRAST_FLOOR);

    // predicteur temporel : mouvement final de l'image precedente, au
    // centre du bloc correspondant, ramene a l'echelle du niveau
    const int step = int(1u << level);
    const int2 tq = min(p * step + step / 2, int2(g_RenderSize) - 1);
    precise const float2 tp = t_Temporal.Load(int3(tq, 0)) * s;

    precise float best = 0.0;
    float2 bestM = 0.0;
    bool any = false;
    float2 prior;
    if ((g_Flags & USR_U_FLAG_TOP) != 0)
    {
        prior = float2(0.0, 0.0);
        for (int oy = -USR_U_COARSE_RADIUS; oy <= USR_U_COARSE_RADIUS; ++oy)
            for (int ox = -USR_U_COARSE_RADIUS; ox <= USR_U_COARSE_RADIUS; ++ox)
                Try(p, float2(ox, oy), prior, j, weight, best, bestM, any);
        [unroll] for (int ty = -1; ty <= 1; ++ty)
            [unroll] for (int tx = -1; tx <= 1; ++tx)
                Try(p, tp + float2(tx, ty), prior, j, weight, best, bestM,
                    any);
    }
    else
    {
        prior = ParentMotion(p, int2(0, 0));
        Try(p, prior, prior, j, weight, best, bestM, any);
        if (level > 0)
        {
            Try(p, ParentMotion(p, int2(-1, 0)), prior, j, weight, best,
                bestM, any);
            Try(p, ParentMotion(p, int2(1, 0)), prior, j, weight, best,
                bestM, any);
            Try(p, ParentMotion(p, int2(0, -1)), prior, j, weight, best,
                bestM, any);
            Try(p, ParentMotion(p, int2(0, 1)), prior, j, weight, best,
                bestM, any);
        }
        Try(p, float2(0.0, 0.0), prior, j, weight, best, bestM, any);
        Try(p, tp, prior, j, weight, best, bestM, any);
        if (level == 0)  // f = 0 : pixel fixe a l'ecran (HUD sans jitter)
            Try(p, g_JitterDelta, prior, j, weight, best, bestM, any);
    }

    // Lucas-Kanade, une iteration, dans l'espace image (f = j - m)
    precise float2 f = j - bestM;
    precise float a11 = 0.0, a12 = 0.0, a22 = 0.0, b1 = 0.0, b2 = 0.0;
    [unroll] for (int oy2 = -USR_U_PATCH_R; oy2 <= USR_U_PATCH_R; ++oy2)
    {
        [unroll] for (int ox2 = -USR_U_PATCH_R; ox2 <= USR_U_PATCH_R; ++ox2)
        {
            precise const float x = float(p.x) + float(ox2) + f.x;
            precise const float y = float(p.y) + float(oy2) + f.y;
            precise const float2 g = BilinearGrad(x, y);
            precise const float it = LoadCur(p + int2(ox2, oy2)) - BilinearPrev(x, y);
            a11 = a11 + g.x * g.x;
            a12 = a12 + g.x * g.y;
            a22 = a22 + g.y * g.y;
            b1 = b1 + g.x * it;
            b2 = b2 + g.y * it;
        }
    }
    precise const float det = a11 * a22 - a12 * a12;
    precise const float tr = a11 + a22;
    precise const float lim = USR_U_LK_COND * tr * tr + 1e-10;
    const bool ok = det > lim;
    precise const float inv = 1.0 / (ok ? det : 1.0);
    precise const float dx = ok ? (a22 * b1 - a12 * b2) * inv : 0.0;
    precise const float dy = ok ? (a11 * b2 - a12 * b1) * inv : 0.0;
    f.x = f.x + clamp(dx, -USR_U_LK_MAX_STEP, USR_U_LK_MAX_STEP);
    f.y = f.y + clamp(dy, -USR_U_LK_MAX_STEP, USR_U_LK_MAX_STEP);
    u_Motion[p] = j - f;
}
