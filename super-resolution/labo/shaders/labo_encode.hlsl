// USR Labo -- l'image « telle qu'un emulateur la voit », pour USR Universel.
//
// Un emulateur ne recoit pas la couleur HDR du moteur, ni sa profondeur, ni
// ses vecteurs de mouvement : seulement l'image finale du jeu, deja
// compressee pour l'ecran et rangee sur 8 bits. Cette passe la fabrique a
// partir du rendu de la scene (meme compression que l'affichage du Labo).

#include "labo_common.hlsli"

cbuffer LaboEncodePass : register(b0)
{
    uint2 g_Size;
};

Texture2D<float4>         t_Source : register(t0);  // couleur lineaire
RWTexture2D<unorm float4> u_Dest   : register(u0);  // RGBA8, [0, 1]

[RootSignature(LABO_ROOT_SIGNATURE)]
[numthreads(8, 8, 1)]
void main(uint3 id : SV_DispatchThreadID)
{
    if (id.x >= g_Size.x || id.y >= g_Size.y)
        return;
    u_Dest[id.xy] = float4(LaboDisplay(t_Source.Load(int3(id.xy, 0)).rgb), 1.0);
}
