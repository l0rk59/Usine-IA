// USR Universel : reduction 2x2 de la pyramide de luminance.
//
// g_LevelSize = taille du niveau lu ; la sortie fait (taille + 1) / 2.
// Jumeau NumPy : usr_ref/flow.py, down2().

#include "usr_u_common.hlsli"

Texture2D<float>   t_Level : register(t0);
RWTexture2D<float> u_Down  : register(u0);

[RootSignature(USR_U_ROOT_SIGNATURE)]
[numthreads(8, 8, 1)]
void main(uint3 id : SV_DispatchThreadID)
{
    const int2 in_size = int2(g_LevelSize);
    const int2 out_size = (in_size + 1) / 2;
    const int2 p = int2(id.xy);
    if (p.x >= out_size.x || p.y >= out_size.y)
        return;
    const int x0 = min(2 * p.x, in_size.x - 1);
    const int x1 = min(2 * p.x + 1, in_size.x - 1);
    const int y0 = min(2 * p.y, in_size.y - 1);
    const int y1 = min(2 * p.y + 1, in_size.y - 1);
    u_Down[p] = (t_Level.Load(int3(x0, y0, 0)) + t_Level.Load(int3(x1, y0, 0)) +
                 t_Level.Load(int3(x0, y1, 0)) + t_Level.Load(int3(x1, y1, 0))) *
                0.25;
}
