// USR Universel : mediane vectorielle 3x3 du mouvement (le voisin le plus
// proche, en distance L1, de tous les autres) -- elimine les aberrants.
// Jumeau NumPy : usr_ref/flow.py, vector_median().

#include "usr_u_common.hlsli"

Texture2D<float2>   t_Motion : register(t0);
RWTexture2D<float2> u_Median : register(u0);

[RootSignature(USR_U_ROOT_SIGNATURE)]
[numthreads(8, 8, 1)]
void main(uint3 id : SV_DispatchThreadID)
{
    const int2 size = int2(g_LevelSize);
    const int2 p = int2(id.xy);
    if (p.x >= size.x || p.y >= size.y)
        return;
    float2 c[9];
    [unroll] for (int k = 0; k < 9; ++k)
    {
        const int2 q = clamp(p + int2(k % 3 - 1, k / 3 - 1), int2(0, 0),
                             size - 1);
        c[k] = t_Motion.Load(int3(q, 0));
    }
    float best = 0.0;
    float2 bestM = c[0];
    [unroll] for (int a = 0; a < 9; ++a)
    {
        precise float s = 0.0;
        [unroll] for (int b = 0; b < 9; ++b)
            s = s + abs(c[a].x - c[b].x) + abs(c[a].y - c[b].y);
        s = floor(s * USR_U_MEDIAN_SCALE + 0.5);
        if (a == 0 || s < best)
        {
            best = s;
            bestM = c[a];
        }
    }
    u_Median[p] = bestM;
}
