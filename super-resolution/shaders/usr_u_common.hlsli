// USR Universel -- declarations communes aux passes du mode sans vecteurs.
//
// Mode pour les images dont on ne connait que les pixels (emulateur,
// capture) : le mouvement est estime (passes usr_u_flow*), puis l'image est
// accumulee par retro-projection du residu (usr_u_residual, usr_u_accumulate).
// Jumeau NumPy : usr_ref/flow.py et usr_ref/universel.py, formule pour
// formule et dans le meme ordre.

#ifndef USR_U_COMMON_HLSLI
#define USR_U_COMMON_HLSLI

#define USR_U_ROOT_SIGNATURE                            \
    "RootConstants(num32BitConstants=20, b0), "         \
    "CBV(b1), "                                         \
    "DescriptorTable(SRV(t0, numDescriptors=8)), "      \
    "DescriptorTable(UAV(u0, numDescriptors=4))"

#define USR_U_FLAG_RESET    1u   // pas d'historique (premiere image, coupure)
#define USR_U_FLAG_NETWORK  2u
#define USR_U_FLAG_DEBUG    4u
#define USR_U_FLAG_TOP      8u   // flot : niveau le plus grossier
#define USR_U_FLAG_PERIOD   16u  // test « meme phase de jitter » disponible
#define USR_U_FLAG_PREV     32u  // une image precedente existe (flot)

// Constantes de usr_ref/flow.py
static const int   USR_U_PATCH_R        = 2;     // motif 5x5
static const float USR_U_COST_SCALE     = 4096.0; // resolution des couts
static const float USR_U_MEDIAN_SCALE   = 1024.0;
static const int   USR_U_COARSE_RADIUS  = 4;
static const float USR_U_LAMBDA         = 0.02;
static const float USR_U_CONTRAST_FLOOR = 0.004;
static const float USR_U_LK_MAX_STEP    = 0.75;
static const float USR_U_LK_COND        = 0.01;
static const float USR_U_CONF_FLOOR     = 0.012;
static const float USR_U_CONF_T0        = 0.6;
static const float USR_U_CONF_T1        = 1.6;

// Constantes de usr_ref/universel.py
static const float USR_U_SIGMA_PROX = 0.47;
static const float USR_U_RANGE_EPS  = 0.02;
static const float USR_U_FEAT_EPS   = 0.01;
static const float USR_U_PI         = 3.14159265358979;
static const float USR_U_FLT_MAX    = 3.402823466e+38;

cbuffer USRUConstants : register(b0)
{
    uint2  g_RenderSize;    // resolution de rendu (niveau 0 du flot)
    uint2  g_DisplaySize;
    uint2  g_LevelSize;     // flot : taille du niveau traite
    uint2  g_ParentSize;    // flot : taille du niveau parent
    float2 g_Jitter;        // jitter de l'image courante (pixels de rendu)
    float2 g_JitterDelta;   // J(t) - J(t-1)
    uint   g_Level;         // flot : niveau de pyramide
    uint   g_Flags;
    float  g_NetStrength;   // 0 = heuristique seule
    float  g_MaxCount;      // longueur maximale de l'historique
    float  g_BoxT1;         // anti-fantomes (sortie de boite -> reactif)
    float  g_Sharpness;     // RCAS, 0..1
    uint   g_Reserved0;
    uint   g_Reserved1;
};

float3 UsrURgbToYCoCg(float3 c)
{
    return float3(0.25 * c.r + 0.5 * c.g + 0.25 * c.b,
                  0.5 * c.r - 0.5 * c.b,
                  -0.25 * c.r + 0.5 * c.g - 0.25 * c.b);
}

float3 UsrUYCoCgToRgb(float3 y)
{
    const float t = y.x - y.z;
    return float3(t + y.y, y.x + y.z, t - y.y);
}

float UsrULuma(float3 c)
{
    return 0.25 * c.r + 0.5 * c.g + 0.25 * c.b;
}

bool UsrUInsideUv(float2 uv)
{
    return uv.x >= 0.0 && uv.x <= 1.0 && uv.y >= 0.0 && uv.y <= 1.0;
}

void UsrUCatmullRomWeights(float f, out float w[4])
{
    w[0] = f * (-0.5 + f * (1.0 - 0.5 * f));
    w[1] = 1.0 + f * f * (-2.5 + 1.5 * f);
    w[2] = f * (0.5 + f * (2.0 - 1.5 * f));
    w[3] = f * f * (-0.5 + 0.5 * f);
}

// Catmull-Rom (16 lectures) de la couleur d'une texture RGBA, aux uv donnes.
float3 UsrUCatmullRom(Texture2D<float4> tex, float2 uv, int2 size)
{
    const float2 pp = uv * float2(size) - 0.5;
    const float2 i1 = floor(pp);
    const float2 f = pp - i1;
    const int2 base = int2(i1);
    float wx[4], wy[4];
    UsrUCatmullRomWeights(f.x, wx);
    UsrUCatmullRomWeights(f.y, wy);
    float3 acc = 0.0;
    [unroll] for (int j = 0; j < 4; ++j)
    {
        const int qy = clamp(base.y + j - 1, 0, size.y - 1);
        [unroll] for (int i = 0; i < 4; ++i)
        {
            const int qx = clamp(base.x + i - 1, 0, size.x - 1);
            acc += tex.Load(int3(qx, qy, 0)).rgb * (wx[i] * wy[j]);
        }
    }
    return acc;
}

// Bilineaire du canal alpha (confiance de l'historique).
float UsrUBilinearAlpha(Texture2D<float4> tex, float2 uv, int2 size)
{
    const float2 pp = uv * float2(size) - 0.5;
    const float2 i1 = floor(pp);
    const float2 f = pp - i1;
    const int2 base = int2(i1);
    const int x0 = clamp(base.x, 0, size.x - 1);
    const int x1 = clamp(base.x + 1, 0, size.x - 1);
    const int y0 = clamp(base.y, 0, size.y - 1);
    const int y1 = clamp(base.y + 1, 0, size.y - 1);
    const float top = tex.Load(int3(x0, y0, 0)).a * (1.0 - f.x) +
                      tex.Load(int3(x1, y0, 0)).a * f.x;
    const float bot = tex.Load(int3(x0, y1, 0)).a * (1.0 - f.x) +
                      tex.Load(int3(x1, y1, 0)).a * f.x;
    return top * (1.0 - f.y) + bot * f.y;
}

float UsrUSigmoid(float x)
{
    return 1.0 / (1.0 + exp(-x));
}

float UsrULogit(float p)
{
    const float q = clamp(p, 1e-3, 1.0 - 1e-3);
    return log(q / (1.0 - q));
}

// Lanczos-2 : sinc(x) sinc(x / 2), nul au-dela de 2.
float UsrULanczos2(float x)
{
    const float ax = abs(x);
    const float pix = USR_U_PI * ax;
    const float s = max(pix, 1e-4);
    const float v = 2.0 * sin(s) * sin(s * 0.5) / (s * s);
    return ax < 2.0 ? (pix < 1e-4 ? 1.0 : v) : 0.0;
}

#endif // USR_U_COMMON_HLSLI
