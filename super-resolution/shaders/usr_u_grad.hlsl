// USR Universel : gradient (differences centrees) d'un niveau de luminance,
// utilise par l'affinage Lucas-Kanade de l'image suivante.
// Jumeau NumPy : usr_ref/flow.py, gradient().

#include "usr_u_common.hlsli"

Texture2D<float>    t_Level : register(t0);
RWTexture2D<float2> u_Grad  : register(u0);

[RootSignature(USR_U_ROOT_SIGNATURE)]
[numthreads(8, 8, 1)]
void main(uint3 id : SV_DispatchThreadID)
{
    const int2 size = int2(g_LevelSize);
    const int2 p = int2(id.xy);
    if (p.x >= size.x || p.y >= size.y)
        return;
    const float gx = (t_Level.Load(int3(min(p.x + 1, size.x - 1), p.y, 0)) -
                      t_Level.Load(int3(max(p.x - 1, 0), p.y, 0))) * 0.5;
    const float gy = (t_Level.Load(int3(p.x, min(p.y + 1, size.y - 1), 0)) -
                      t_Level.Load(int3(p.x, max(p.y - 1, 0), 0))) * 0.5;
    u_Grad[p] = float2(gx, gy);
}
