// Le reseau de USR : 10 entrees -> 16 -> 16 -> 2, activations ReLU.
//
// 482 poids dans un tampon constant de 121 float4 (b1), dans l'ordre
// W1[16][10], b1[16], W2[16][16], b2[16], W3[2][16], b3[2] -- le format
// .bin produit par `python -m usr_ref entrainer`. Toutes les boucles sont
// deroulees : chaque poids est lu a une adresse connue a la compilation.
//
// Environ 420 multiplications-additions par pixel. Sur Xbox Series X
// (12 TFLOPS FP32, le double en FP16 compacte) c'est l'ordre de la
// demi-milliseconde en 4K, a mesurer sur la console. Definir
// USR_NETWORK_HALF passe les activations en min16float : le compilateur
// peut alors utiliser les instructions FP16 compactees de RDNA 2.

#ifndef USR_NETWORK_HLSLI
#define USR_NETWORK_HLSLI

#define USR_NET_INPUTS  10
#define USR_NET_HIDDEN  16
#define USR_NET_OUTPUTS 2

#define USR_NET_B1 160
#define USR_NET_W2 176
#define USR_NET_B2 432
#define USR_NET_W3 448
#define USR_NET_B3 480

#ifdef USR_NETWORK_HALF
typedef min16float usr_netf;
#else
typedef float usr_netf;
#endif

cbuffer USRNetwork : register(b1)
{
    float4 g_Net[121];
};

usr_netf UsrNetW(uint i)
{
    return (usr_netf)g_Net[i >> 2][i & 3];
}

float2 UsrNetwork(float x[USR_NET_INPUTS])
{
    usr_netf h1[USR_NET_HIDDEN];
    [unroll] for (uint j = 0; j < USR_NET_HIDDEN; ++j)
    {
        usr_netf s = UsrNetW(USR_NET_B1 + j);
        [unroll] for (uint i = 0; i < USR_NET_INPUTS; ++i)
            s += UsrNetW(j * USR_NET_INPUTS + i) * (usr_netf)x[i];
        h1[j] = max(s, (usr_netf)0);
    }

    usr_netf h2[USR_NET_HIDDEN];
    [unroll] for (uint k = 0; k < USR_NET_HIDDEN; ++k)
    {
        usr_netf s = UsrNetW(USR_NET_B2 + k);
        [unroll] for (uint i = 0; i < USR_NET_HIDDEN; ++i)
            s += UsrNetW(USR_NET_W2 + k * USR_NET_HIDDEN + i) * h1[i];
        h2[k] = max(s, (usr_netf)0);
    }

    float2 o;
    [unroll] for (uint m = 0; m < USR_NET_OUTPUTS; ++m)
    {
        usr_netf s = UsrNetW(USR_NET_B3 + m);
        [unroll] for (uint i = 0; i < USR_NET_HIDDEN; ++i)
            s += UsrNetW(USR_NET_W3 + m * USR_NET_HIDDEN + i) * h2[i];
        o[m] = (float)s;
    }
    return o;
}

#endif // USR_NETWORK_HLSLI
