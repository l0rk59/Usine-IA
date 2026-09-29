// USR -- Usine Super Resolution
//
// Upscaler temporel a petit reseau neuronal pour Direct3D 12 : le jeu rend
// en basse resolution avec un leger decalage (jitter) different a chaque
// image, USR accumule ces images et reconstruit la resolution d'affichage.
//
// Cible principale : Xbox Series X|S (GPU AMD RDNA 2) ; fonctionne sur tout
// PC Direct3D 12 (Shader Model 6.0). Voir docs/INTEGRATION.md.
//
// Utilisation minimale :
//
//   usr::CreateDesc cd = {};
//   cd.device = device;
//   usr::GetRenderSize(usr::QualityMode::Performance, 3840, 2160,
//                      &cd.renderWidth, &cd.renderHeight);   // 1920x1080
//   cd.displayWidth = 3840; cd.displayHeight = 2160;
//   usr::Context* ctx = nullptr;
//   usr::CreateContext(cd, &ctx);
//
//   // a chaque image :
//   float jx, jy;
//   usr::GetJitterOffset(frame, usr::GetJitterPhaseCount(1920, 3840),
//                        &jx, &jy);
//   ... decaler la matrice de projection de (-2*jx/w, +2*jy/h), rendre ...
//   usr::DispatchDesc d = {};  d.commandList = cl; d.color = ...;
//   d.jitterX = jx; d.jitterY = jy; ...
//   usr::Dispatch(ctx, d);
//   ... re-lier SES tas de descripteurs (USR lie le sien) ...

#pragma once

#include <cstdint>

#if defined(_GAMING_XBOX_SCARLETT)
#include <d3d12_xs.h>
#elif defined(_GAMING_XBOX_XBOXONE)
#include <d3d12_x.h>
#else
#include <d3d12.h>
#endif

namespace usr {

constexpr uint32_t kVersionMajor = 0;
constexpr uint32_t kVersionMinor = 1;

enum class Result : int32_t {
    Ok = 0,
    InvalidArgument,
    OutOfMemory,
    DeviceError,
    // Generation d'images : pas encore de flot (premiere image apres une
    // creation ou une remise a zero). Montrer l'image reelle.
    NotReady,
};

// Rapport affichage / rendu, par axe.
enum class QualityMode : uint32_t {
    Native,            // 1.0x : anticrenelage seul (comme "DLAA")
    Quality,           // 1.5x
    Balanced,          // 1.7x
    Performance,       // 2.0x : 1080p -> 4K
    UltraPerformance,  // 3.0x : 720p  -> 4K
};

enum CreateFlags : uint32_t {
    kCreateNone = 0,
    // Heuristique seule, sans le reseau (un peu plus rapide, moins fin).
    kCreateDisableNetwork = 1u << 0,
};

struct ShaderBytecode {
    const void* data = nullptr;
    size_t size = 0;
};

struct CreateDesc {
    ID3D12Device* device = nullptr;
    uint32_t renderWidth = 0;    // resolution de rendu (fixe pour ce contexte)
    uint32_t renderHeight = 0;
    uint32_t displayWidth = 0;   // resolution de sortie
    uint32_t displayHeight = 0;
    // Nombre d'images que le CPU peut avoir d'avance sur le GPU : USR garde
    // autant de jeux de descripteurs pour ne jamais ecraser ceux en vol.
    uint32_t maxFramesInFlight = 3;
    uint32_t flags = kCreateNone;

    // Poids du reseau (format .bin de usr_ref, 484 floats). nullptr : poids
    // par defaut compiles dans la bibliotheque.
    const float* weights = nullptr;
    uint32_t weightCount = 0;

    // Bytecode des trois passes. Vide : bytecode integre a la compilation
    // (DXIL pour PC ; pour la Xbox en GDK, compilez avec le dxc du GDK et
    // passez le resultat ici ou via l'option CMake USR_DXC).
    ShaderBytecode prepareCS;
    ShaderBytecode accumulateCS;
    ShaderBytecode sharpenCS;
};

// Etats attendus a l'appel de Dispatch (et laisses tels quels a la fin) :
//   color, depth, motionVectors : D3D12_RESOURCE_STATE_NON_PIXEL_SHADER_RESOURCE
//   output                      : D3D12_RESOURCE_STATE_UNORDERED_ACCESS
struct DispatchDesc {
    ID3D12GraphicsCommandList* commandList = nullptr;

    ID3D12Resource* color = nullptr;          // resolution de rendu, lineaire
    ID3D12Resource* depth = nullptr;          // resolution de rendu
    ID3D12Resource* motionVectors = nullptr;  // resolution de rendu, RG
    ID3D12Resource* output = nullptr;         // resolution d'affichage, UAV
                                              // (pas sRGB : InvalidArgument)

    // Formats des vues ; DXGI_FORMAT_UNKNOWN = deduit de la ressource
    // (les formats "typeless" et de profondeur sont convertis).
    DXGI_FORMAT colorFormat = DXGI_FORMAT_UNKNOWN;
    DXGI_FORMAT depthFormat = DXGI_FORMAT_UNKNOWN;
    DXGI_FORMAT motionFormat = DXGI_FORMAT_UNKNOWN;
    DXGI_FORMAT outputFormat = DXGI_FORMAT_UNKNOWN;

    // Position de l'echantillon dans le pixel de rendu, dans [-0.5, 0.5] :
    // le pixel (i, j) contient la scene vue en ((i + 0.5 + jitterX) / w,
    // (j + 0.5 + jitterY) / h), y vers le bas. Utilisez GetJitterOffset.
    float jitterX = 0.0f;
    float jitterY = 0.0f;

    // Conversion des vecteurs du moteur vers USR : uv_precedent =
    // uv - mv * motionScale. Vecteurs en pixels "courant - precedent" :
    // (1/w, 1/h). En NDC "courant - precedent" : (0.5, -0.5).
    float motionScaleX = 1.0f;
    float motionScaleY = 1.0f;

    // 1 / profondeur lineaire = profondeur * depthP0 + depthP1.
    // Utilisez GetDepthParams.
    float depthP0 = 1.0f;
    float depthP1 = 0.0f;

    float exposure = 1.0f;   // multiplie la couleur avant accumulation
    float sharpness = 0.0f;  // 0..1
    bool reset = false;      // coupure de camera, chargement : oublie tout

    // --- Reglages avances (par defaut : ceux de l'entrainement) ----------
    // Influence du reseau : 0 = heuristique seule, 1 = tel qu'entraine,
    // jusqu'a 4 = decisions amplifiees (pour experimenter).
    float networkStrength = 1.0f;
    // Nombre maximal d'images accumulees (1..64) : plus = plus lisse et
    // plus fin a l'arret, mais plus lent a oublier.
    float historyLength = 10.0f;
    // Largeur de la boite anti-fantomes, en ecarts-types (0.25..8) :
    // petit = rejette vite l'historique (moins de trainees, plus de
    // scintillement), grand = le garde (plus de detail, plus de trainees).
    float antiGhosting = 1.25f;
    // Largeur du noyau d'accumulation (0.25..4) : < 1 plus net mais plus
    // bruite, > 1 plus doux.
    float kernelWidth = 1.0f;

    // Optionnel : texture de diagnostic en resolution d'affichage, etat
    // UNORDERED_ACCESS. Recoit par pixel (alpha, beta, confiance, desocclusion).
    ID3D12Resource* debugOutput = nullptr;
    DXGI_FORMAT debugFormat = DXGI_FORMAT_UNKNOWN;
};

class Context;

Result CreateContext(const CreateDesc& desc, Context** outContext);
// Le GPU ne doit plus utiliser le contexte (attendre la fence du jeu).
void DestroyContext(Context* context);

// Enregistre les trois passes dans desc.commandList. USR lie son propre tas
// de descripteurs (SetDescriptorHeaps) : le jeu doit re-lier le sien apres.
Result Dispatch(Context* context, const DispatchDesc& desc);

// Remplace les poids du reseau. Le GPU ne doit pas etre en train
// d'executer une commande USR (appeler entre deux images, apres la fence).
Result SetWeights(Context* context, const float* weights, uint32_t count);

// --- Aides ---------------------------------------------------------------

float GetUpscaleRatio(QualityMode mode);
void GetRenderSize(QualityMode mode, uint32_t displayWidth,
                   uint32_t displayHeight, uint32_t* renderWidth,
                   uint32_t* renderHeight);

// Nombre de positions de jitter a parcourir : plus l'agrandissement est
// fort, plus il faut d'echantillons par pixel d'affichage.
uint32_t GetJitterPhaseCount(uint32_t renderWidth, uint32_t displayWidth);
// Suite de Halton (2, 3), dans [-0.5, 0.5]. frameIndex croissant.
void GetJitterOffset(uint32_t frameIndex, uint32_t phaseCount, float* x,
                     float* y);

// Parametres de linearisation pour une projection perspective.
// reversedZ : proche = 1, loin = 0. infiniteFar : pas de plan lointain.
void GetDepthParams(float nearZ, float farZ, bool reversedZ,
                    bool infiniteFar, float* p0, float* p1);

// ===========================================================================
// USR Universel : sans profondeur ni vecteurs de mouvement
// ===========================================================================
//
// Pour les images dont on ne connait que les pixels : emulateur (Xenia),
// capture, lecteur video. USR estime lui-meme le mouvement (flot optique
// sur GPU), puis accumule par retro-projection du residu : sans information
// nouvelle l'image reste celle d'un bon agrandissement spatial, et chaque
// mouvement (ou jitter) apporte du detail. Voir docs/XENIA.md.
//
//   usr::UniversalCreateDesc cd = {};
//   cd.device = device;
//   cd.renderWidth = 1280; cd.renderHeight = 720;      // image du jeu
//   cd.displayWidth = 3840; cd.displayHeight = 2160;   // sortie
//   cd.jitterPeriod = 0;   // niveau 1 : l'emulateur ne decale rien
//   usr::UniversalContext* u = nullptr;
//   usr::CreateUniversalContext(cd, &u);
//   // a chaque nouvelle image du jeu :
//   usr::UniversalDispatchDesc d = {};
//   d.commandList = cl; d.color = image; d.output = sortie;
//   usr::DispatchUniversal(u, d);
//
// Niveau 2 (l'emulateur decale le rendu 3D d'un jitter connu) : prendre
// cd.jitterPeriod = GetUniversalJitterPeriod(...) et, a chaque image,
// d.jitterX/Y = GetUniversalJitter(...), le meme que celui injecte.

enum class UniversalPass : uint32_t {
    Luma = 0,     // usr_u_luma
    Down,         // usr_u_down
    Gradient,     // usr_u_grad
    Flow,         // usr_u_flow
    Median,       // usr_u_median
    Finalize,     // usr_u_finalize
    Residual,     // usr_u_residual
    Accumulate,   // usr_u_accumulate
    Output,       // usr_u_output
    InterpDiff,   // usr_u_interp_ecart (generation d'images)
    Interpolate,  // usr_u_interp
    Count
};

struct UniversalCreateDesc {
    ID3D12Device* device = nullptr;
    uint32_t renderWidth = 0;    // taille de l'image recue (fixe)
    uint32_t renderHeight = 0;
    uint32_t displayWidth = 0;   // taille de sortie
    uint32_t displayHeight = 0;
    uint32_t maxFramesInFlight = 3;
    uint32_t flags = kCreateNone;   // kCreateDisableNetwork
    // Periode de la suite de jitter injectee (0 : pas de jitter). Sert au
    // test exact « meme phase » qui fige les zones immobiles.
    uint32_t jitterPeriod = 0;
    // Poids du reseau universel (484 floats). nullptr : poids integres.
    const float* weights = nullptr;
    uint32_t weightCount = 0;
    // Bytecode des passes (vide : integre a la compilation).
    ShaderBytecode shaders[static_cast<uint32_t>(UniversalPass::Count)];
};

// Etats attendus a l'appel (et laisses tels quels) :
//   color  : D3D12_RESOURCE_STATE_NON_PIXEL_SHADER_RESOURCE
//   output : D3D12_RESOURCE_STATE_UNORDERED_ACCESS
struct UniversalDispatchDesc {
    ID3D12GraphicsCommandList* commandList = nullptr;
    // Image du jeu telle qu'elle serait affichee (valeurs [0, 1], deja
    // compressees pour l'ecran). Format lu tel quel : utiliser une vue
    // UNORM, pas sRGB, pour garder les valeurs de l'ecran.
    ID3D12Resource* color = nullptr;
    ID3D12Resource* output = nullptr;   // resolution d'affichage, UAV
    DXGI_FORMAT colorFormat = DXGI_FORMAT_UNKNOWN;
    DXGI_FORMAT outputFormat = DXGI_FORMAT_UNKNOWN;

    // Jitter injecte par l'emulateur pour CETTE image (pixels de rendu,
    // [-0.5, 0.5]), 0 au niveau 1.
    float jitterX = 0.0f;
    float jitterY = 0.0f;
    bool reset = false;          // coupure, chargement : oublie tout

    // --- Reglages (modifiables a chaque image) ---------------------------
    float sharpness = 0.0f;      // accentuation RCAS, 0..1
    float networkStrength = 1.0f;  // 0 = regles de base seules .. 4
    float historyLength = 10.0f;   // images accumulees au plus, 1..64
    // Anti-fantomes : sortie de boite qui rend un pixel totalement
    // reactif (0.05..4). Petit = oublie vite (moins de trainees, moins de
    // detail), grand = garde l'historique.
    float antiGhosting = 0.3f;

    // Optionnel (UNORDERED_ACCESS, resolution d'affichage) : par pixel
    // (reactivite, gain, confiance / max, confiance du flot).
    ID3D12Resource* debugOutput = nullptr;
    DXGI_FORMAT debugFormat = DXGI_FORMAT_UNKNOWN;
};

class UniversalContext;

Result CreateUniversalContext(const UniversalCreateDesc& desc,
                              UniversalContext** outContext);
void DestroyUniversalContext(UniversalContext* context);
// Enregistre les passes dans desc.commandList. Comme Dispatch, lie son
// propre tas de descripteurs : re-lier le sien apres.
Result DispatchUniversal(UniversalContext* context,
                         const UniversalDispatchDesc& desc);
Result SetUniversalWeights(UniversalContext* context, const float* weights,
                           uint32_t count);

// --- Generation d'images ---------------------------------------------------
//
// Une image intermediaire entre les deux dernieres sorties, avec le flot que
// DispatchUniversal vient d'estimer : a appeler apres DispatchUniversal de
// l'image « current » et avant le suivant. Ou le flot ne sait pas suivre
// (desocclusion, motif periodique qui defile), l'image reste un fondu ou
// l'image courante seule : voir docs/GENERATION.md, mesures comprises.
//
// Etats attendus a l'appel (et laisses tels quels) :
//   previous, current : D3D12_RESOURCE_STATE_NON_PIXEL_SHADER_RESOURCE
//   output            : D3D12_RESOURCE_STATE_UNORDERED_ACCESS
struct UniversalInterpolateDesc {
    ID3D12GraphicsCommandList* commandList = nullptr;
    ID3D12Resource* previous = nullptr;  // sortie de l'image precedente
    ID3D12Resource* current = nullptr;   // sortie de cette image
    ID3D12Resource* output = nullptr;    // resolution d'affichage, UAV
    DXGI_FORMAT previousFormat = DXGI_FORMAT_UNKNOWN;
    DXGI_FORMAT currentFormat = DXGI_FORMAT_UNKNOWN;
    DXGI_FORMAT outputFormat = DXGI_FORMAT_UNKNOWN;
    float time = 0.5f;  // 0 : previous .. 1 : current
};

// Au plus kMaxInterpolationsPerFrame appels par image reelle (x4).
constexpr uint32_t kMaxInterpolationsPerFrame = 3;

// NotReady s'il n'y a pas encore de flot. Comme Dispatch, lie son propre
// tas de descripteurs : re-lier le sien apres.
Result InterpolateUniversal(UniversalContext* context,
                            const UniversalInterpolateDesc& desc);

// Jitter du niveau 2 : grille ordonnee (2x2, 3x3) quand le rapport est
// entier -- chaque pixel d'affichage recoit un echantillon exactement en
// son centre toutes les n*n images -- sinon Halton (2, 3).
uint32_t GetUniversalJitterPeriod(uint32_t renderWidth, uint32_t renderHeight,
                                  uint32_t displayWidth,
                                  uint32_t displayHeight);
void GetUniversalJitter(uint32_t frameIndex, uint32_t renderWidth,
                        uint32_t renderHeight, uint32_t displayWidth,
                        uint32_t displayHeight, float* x, float* y);

} // namespace usr
