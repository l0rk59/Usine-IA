// USR Universel, generation d'images : ce que les deux passes partagent.
// Jumeau NumPy : usr_ref/interpolation.py, formule pour formule.
//
// Flot : celui que la passe finalize vient d'ecrire pour l'image courante
// (pixels de rendu, « ou etait ce point dans l'image precedente : x - m »).
// Images : les deux dernieres sorties de USR, a la resolution d'affichage.

#ifndef USR_U_INTERP_HLSLI
#define USR_U_INTERP_HLSLI

#include "usr_u_common.hlsli"

// Constantes de usr_ref/interpolation.py
static const float USR_U_SIGMA_ACCORD    = 0.12;
static const float USR_U_SEUIL_FLOT      = 2.0;
static const float USR_U_POIDS_SUR_PLACE = 0.5;

Texture2D<float4> t_Prev       : register(t0);  // sortie precedente
Texture2D<float4> t_Cur        : register(t1);  // sortie courante
Texture2D<float2> t_Motion     : register(t2);  // flot courant (rendu)
Texture2D<float2> t_MotionPrev : register(t3);  // flot precedent (rendu)
Texture2D<float2> t_Ecart      : register(t4);  // passe 1 : (e flot, e 0)

int2 UsrUNearestIndex(float2 uv, int2 size)
{
    return clamp(int2(floor(uv * float2(size))), int2(0, 0), size - 1);
}

float2 UsrUMotionUv(float2 uv)
{
    const int2 rs = int2(g_RenderSize);
    return t_Motion.Load(int3(UsrUNearestIndex(uv, rs), 0)) /
           float2(g_RenderSize);
}

float3 UsrUBilinearRgb(Texture2D<float4> tex, float2 uv, int2 size)
{
    const float2 pp = uv * float2(size) - 0.5;
    const float2 i1 = floor(pp);
    const float2 f = pp - i1;
    const int2 base = int2(i1);
    const int x0 = clamp(base.x, 0, size.x - 1);
    const int x1 = clamp(base.x + 1, 0, size.x - 1);
    const int y0 = clamp(base.y, 0, size.y - 1);
    const int y1 = clamp(base.y + 1, 0, size.y - 1);
    const float3 top = tex.Load(int3(x0, y0, 0)).rgb * (1.0 - f.x) +
                       tex.Load(int3(x1, y0, 0)).rgb * f.x;
    const float3 bot = tex.Load(int3(x0, y1, 0)).rgb * (1.0 - f.x) +
                       tex.Load(int3(x1, y1, 0)).rgb * f.x;
    return top * (1.0 - f.y) + bot * f.y;
}

// Pixel d'affichage p : uv, puis le flot lu deux fois (en p, puis a la
// position courante estimee), comme interpoler().
void UsrUInterpMotion(int2 p, out float2 uv, out float2 uvc0, out float2 m1)
{
    const float t = g_Time;
    uv = (float2(p) + 0.5) / float2(g_DisplaySize);
    const float2 m0 = UsrUMotionUv(uv);
    uvc0 = uv + (1.0 - t) * m0;
    m1 = UsrUMotionUv(uvc0);
}

struct UsrUHypothese
{
    float3 cc;
    float3 cp;
    bool   dedans;
    float  ecart;
};

UsrUHypothese UsrUInterpHypothese(float2 uv, float2 m)
{
    const float t = g_Time;
    const int2 ds = int2(g_DisplaySize);
    const float2 uvc = uv + (1.0 - t) * m;
    const float2 uvp = uv - t * m;
    UsrUHypothese h;
    h.cc = UsrUBilinearRgb(t_Cur, uvc, ds);
    h.cp = UsrUBilinearRgb(t_Prev, uvp, ds);
    h.dedans = UsrUInsideUv(uvp);
    h.ecart = abs(UsrULuma(h.cc) - UsrULuma(h.cp));
    return h;
}

#endif // USR_U_INTERP_HLSLI
