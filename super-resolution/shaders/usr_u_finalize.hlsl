// USR Universel : fin du flot au niveau de rendu.
//
// * confiance : residu du meilleur appariement rapporte au contraste local ;
// * pixel identique (16 bits) a l'image precedente : fixe a l'ecran, f = 0,
//   et « non soumis au jitter » si le jitter a bouge (HUD) ;
// * identique a l'image de meme phase de jitter : scene immobile, m = 0.
// u0 : mouvement final (pixels de rendu) ; u1 : (confiance, suit le jitter,
// fixe, 0) en RGBA8.
// Jumeau NumPy : usr_ref/flow.py, fin de FlowEstimator.__call__.

#include "usr_u_common.hlsli"

Texture2D<float>    t_Cur      : register(t0); // luminance courante
Texture2D<float>    t_Prev     : register(t1); // luminance precedente
Texture2D<float2>   t_Motion   : register(t2); // mouvement (mediane, niv. 0)
Texture2D<uint>     t_Cur16    : register(t3);
Texture2D<uint>     t_Prev16   : register(t4); // image t - 1
Texture2D<uint>     t_Phase16  : register(t5); // image t - P
RWTexture2D<float2> u_Final    : register(u0);
RWTexture2D<float4> u_Aux      : register(u1);

static int2 s_Size;

float LoadCur(int2 p)
{
    return t_Cur.Load(int3(clamp(p, int2(0, 0), s_Size - 1), 0));
}

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

bool ExactSame(Texture2D<uint> a, Texture2D<uint> b, int2 p)
{
    uint diff = 0u;
    [unroll] for (int oy = -USR_U_PATCH_R; oy <= USR_U_PATCH_R; ++oy)
    {
        [unroll] for (int ox = -USR_U_PATCH_R; ox <= USR_U_PATCH_R; ++ox)
        {
            const int3 q = int3(clamp(p + int2(ox, oy), int2(0, 0),
                                      s_Size - 1), 0);
            diff |= a.Load(q) ^ b.Load(q);
        }
    }
    return diff == 0u;
}

[RootSignature(USR_U_ROOT_SIGNATURE)]
[numthreads(8, 8, 1)]
void main(uint3 id : SV_DispatchThreadID)
{
    s_Size = int2(g_RenderSize);
    const int2 p = int2(id.xy);
    if (p.x >= s_Size.x || p.y >= s_Size.y)
        return;

    if ((g_Flags & USR_U_FLAG_PREV) == 0)
    {
        // premiere image : rien a comparer
        u_Final[p] = float2(0.0, 0.0);
        u_Aux[p] = float4(1.0, 1.0, 0.0, 0.0);
        return;
    }

    float2 m = t_Motion.Load(int3(p, 0));
    precise const float2 dj = g_JitterDelta;

    precise float res = 0.0;
    precise float taps[25];
    precise float total = 0.0;
    [unroll] for (int k = 0; k < 25; ++k)
    {
        const int ox = k % 5 - 2;
        const int oy = k / 5 - 2;
        taps[k] = LoadCur(p + int2(ox, oy));
        total = total + taps[k];
        precise const float q = BilinearPrev(float(p.x) + float(ox) + (dj.x - m.x),
                                     float(p.y) + float(oy) + (dj.y - m.y));
        res = res + abs(taps[k] - q);
    }
    precise const float mean = total * (1.0 / 25.0);
    precise float contrast = 0.0;
    [unroll] for (int k2 = 0; k2 < 25; ++k2)
        contrast = contrast + abs(taps[k2] - mean);
    precise const float rel = res / (contrast + 25.0 * USR_U_CONF_FLOOR);
    float conf = saturate((rel - USR_U_CONF_T0) / (USR_U_CONF_T1 - USR_U_CONF_T0));
    float jflag = 1.0;
    float isStatic = 0.0;

    const bool same = ExactSame(t_Cur16, t_Prev16, p);
    if (same)
    {
        m = dj;
        if (dj.x != 0.0 || dj.y != 0.0)
            jflag = 0.0;
    }
    bool samePhase = false;
    if ((g_Flags & USR_U_FLAG_PERIOD) != 0)
    {
        samePhase = !same && ExactSame(t_Cur16, t_Phase16, p);
        if (samePhase)
            m = float2(0.0, 0.0);
    }
    if (same || samePhase)
    {
        conf = 0.0;
        isStatic = 1.0;
    }
    u_Final[p] = m;
    u_Aux[p] = float4(conf, jflag, isStatic, 0.0);
}
