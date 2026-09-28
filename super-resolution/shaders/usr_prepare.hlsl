// Passe 1 (resolution de rendu) : dilatation des vecteurs de mouvement et
// detection des zones desoccluses.
//
// Jumeau NumPy : usr_ref/core.py, fonction prepare().

#include "usr_common.hlsli"

Texture2D<float>    t_Depth        : register(t0); // profondeur materielle
Texture2D<float2>   t_Motion       : register(t1); // vecteurs du moteur
Texture2D<float>    t_PrevInvZ     : register(t2); // u_DilatedInvZ precedent

RWTexture2D<float2> u_DilatedMotion : register(u0);
RWTexture2D<float>  u_DilatedInvZ   : register(u1);
RWTexture2D<float>  u_Disocclusion  : register(u2);

float LoadInvZ(int2 p)
{
    return t_Depth.Load(int3(p, 0)) * g_DepthP0 + g_DepthP1;
}

[RootSignature(USR_ROOT_SIGNATURE)]
[numthreads(8, 8, 1)]
void main(uint3 id : SV_DispatchThreadID)
{
    const int2 size = int2(g_RenderSize);
    const int2 p = int2(id.xy);
    if (p.x >= size.x || p.y >= size.y)
        return;

    // Le vecteur retenu est celui du voisin le plus proche de la camera :
    // le bord d'un objet suit l'objet, pas le decor derriere lui.
    float best = LoadInvZ(p);
    float2 bestMv = t_Motion.Load(int3(p, 0)) * g_MotionScale;
    [unroll] for (int dy = -1; dy <= 1; ++dy)
    {
        [unroll] for (int dx = -1; dx <= 1; ++dx)
        {
            if (dx == 0 && dy == 0)
                continue;
            const int2 q = clamp(p + int2(dx, dy), int2(0, 0), size - 1);
            const float z = LoadInvZ(q);
            if (z > best)
            {
                best = z;
                bestMv = t_Motion.Load(int3(q, 0)) * g_MotionScale;
            }
        }
    }

    // Ou etait ce point a l'image precedente, et qu'y avait-il devant ?
    const float2 uv = (float2(p) + 0.5 + g_Jitter) / float2(size);
    const float2 puv = uv - bestMv;
    const int2 p0 = int2(floor(puv * float2(size) - 0.5));
    const float zCur = 1.0 / max(best, 1e-8);
    float closest = USR_FLT_MAX;
    [unroll] for (int oy = 0; oy <= 1; ++oy)
    {
        [unroll] for (int ox = 0; ox <= 1; ++ox)
        {
            const int2 q = clamp(p0 + int2(ox, oy), int2(0, 0), size - 1);
            const float zPrev = 1.0 / max(t_PrevInvZ.Load(int3(q, 0)), 1e-8);
            // > 0 : une surface plus proche occupait cet endroit, donc ce
            // qu'on voit maintenant etait cache.
            closest = min(closest, (zCur - zPrev) / zCur);
        }
    }
    float disocc = saturate((closest - USR_DISOCC_T0) /
                            (USR_DISOCC_T1 - USR_DISOCC_T0));
    if (!UsrInsideUv(puv) || (g_Flags & USR_FLAG_RESET) != 0)
        disocc = 1.0;

    u_DilatedMotion[p] = bestMv;
    u_DilatedInvZ[p] = best;
    u_Disocclusion[p] = disocc;
}
