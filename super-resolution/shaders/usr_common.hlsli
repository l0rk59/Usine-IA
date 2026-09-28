// USR -- Usine Super Resolution : declarations communes aux trois passes.
//
// Cible : Direct3D 12, Shader Model 6.0 minimum (compute uniquement), donc
// Xbox Series X|S (GPU AMD RDNA 2) comme n'importe quel PC DX12.
// Toutes les formules ont leur jumeau en NumPy dans usr_ref/core.py ; les
// constantes ci-dessous doivent rester egales a celles de ce fichier.

#ifndef USR_COMMON_HLSLI
#define USR_COMMON_HLSLI

// Signature racine commune aux trois passes, embarquee dans le bytecode :
// le code C++ la recupere avec CreateRootSignature(bytecode du shader).
#define USR_ROOT_SIGNATURE                              \
    "RootConstants(num32BitConstants=16, b0), "         \
    "CBV(b1), "                                         \
    "DescriptorTable(SRV(t0, numDescriptors=4)), "      \
    "DescriptorTable(UAV(u0, numDescriptors=3))"

#define USR_FLAG_RESET   1u
#define USR_FLAG_NETWORK 2u

static const float USR_SIGMA_FRESH  = 0.60;  // noyau spatial sans historique
static const float USR_KERNEL_COUNT = 3.0;   // confiance -> noyau etroit
static const float USR_DISOCC_T0    = 0.02;  // ecart relatif de profondeur
static const float USR_DISOCC_T1    = 0.06;
static const float USR_SHARPEN_PEAK = 0.2;
static const float USR_EPS_SIGMA    = 0.004;
static const float USR_FLT_MAX      = 3.402823466e+38;

// 16 valeurs 32 bits : passees en constantes racine (root constants).
cbuffer USRConstants : register(b0)
{
    uint2  g_RenderSize;
    uint2  g_DisplaySize;
    float2 g_Jitter;        // position de l'echantillon dans le pixel de rendu
    float2 g_MotionScale;   // vecteurs du moteur -> uv (uv_prec = uv - mv)
    float  g_DepthP0;       // 1 / profondeur lineaire = d * P0 + P1
    float  g_DepthP1;
    float  g_Exposure;
    float  g_Sharpness;     // 0 = pas d'accentuation, 1 = maximum
    uint   g_Flags;
    float  g_SigmaSharp;    // noyau d'accumulation, en pixels de rendu
    float  g_MaxCount;      // confiance maximale de l'historique
    float  g_ClipGamma;     // largeur de la boite de recadrage (en sigma)
};

// Compression reversible : l'accumulation se fait dans [0, 1[ meme en HDR,
// ce qui evite qu'un reflet tres lumineux ne "bave" pendant des images.
float3 UsrTonemap(float3 c)
{
    return c / (1.0 + max(c.r, max(c.g, c.b)));
}

float3 UsrUntonemap(float3 y)
{
    return y / max(1.0 - max(y.r, max(y.g, y.b)), 1e-3);
}

float3 UsrRgbToYCoCg(float3 c)
{
    return float3(0.25 * c.r + 0.5 * c.g + 0.25 * c.b,
                  0.5 * c.r - 0.5 * c.b,
                  -0.25 * c.r + 0.5 * c.g - 0.25 * c.b);
}

float3 UsrYCoCgToRgb(float3 y)
{
    float t = y.x - y.z;
    return float3(t + y.y, y.x + y.z, t - y.y);
}

float UsrSigmoid(float x)
{
    return 1.0 / (1.0 + exp(-x));
}

bool UsrInsideUv(float2 uv)
{
    return uv.x >= 0.0 && uv.x <= 1.0 && uv.y >= 0.0 && uv.y <= 1.0;
}

#endif // USR_COMMON_HLSLI
