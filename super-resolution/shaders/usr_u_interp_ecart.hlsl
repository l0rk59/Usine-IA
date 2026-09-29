// USR Universel, generation d'images, passe 1 (resolution d'affichage) :
// ecart de luminance entre les deux images recalees, pour chacune des deux
// hypotheses (« suivre le flot », « rester sur place »). La passe 2 en
// fait la moyenne 3x3 : un pixel isole qui s'accorde par hasard ne decide
// pas seul, et cette moyenne demande les ecarts des voisins, calcules ici
// une fois pour toutes.
// Jumeau NumPy : usr_ref/interpolation.py, interpoler().

#include "usr_u_interp.hlsli"

RWTexture2D<float2> u_Ecart : register(u0);

[RootSignature(USR_U_ROOT_SIGNATURE)]
[numthreads(8, 8, 1)]
void main(uint3 id : SV_DispatchThreadID)
{
    const int2 p = int2(id.xy);
    if (p.x >= int(g_DisplaySize.x) || p.y >= int(g_DisplaySize.y))
        return;
    float2 uv, uvc0, m1;
    UsrUInterpMotion(p, uv, uvc0, m1);
    const UsrUHypothese h1 = UsrUInterpHypothese(uv, m1);
    const UsrUHypothese h0 = UsrUInterpHypothese(uv, float2(0.0, 0.0));
    u_Ecart[p] = float2(h1.ecart, h0.ecart);
}
