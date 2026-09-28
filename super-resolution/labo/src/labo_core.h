// USR Labo -- le "cerveau" de l'application, sans aucune API graphique ni
// systeme : reglages, menu pilote a la manette, animation de la scene,
// texte a afficher. Compile et teste tel quel sous Linux
// (labo/tests/test_labo_core.cpp) ; les couches Xbox (UWP) et PC (Win32)
// ne font que lui passer la manette et dessiner ce qu'il decide.

#pragma once

#include <cstdint>
#include <string>
#include <vector>

#include "labo_text.h"

namespace labo {

// --- Ce qu'on peut afficher dans chaque moitie de l'ecran ----------------

enum class View : uint32_t {
    UsrIA,         // USR avec le reseau
    UsrSansIA,     // USR, heuristique seule
    UsrUniversel,  // USR Universel : sans vecteurs, comme dans un emulateur
    Bilineaire,    // agrandissement naif, sans jitter
    Verite,        // rendu direct a la resolution d'affichage
    EntreeBrute,   // l'image recue par USR, pixels agrandis
    Alpha,         // diagnostic : poids de l'image courante
    Beta,          // diagnostic : historique garde sans recadrage
    Confiance,     // diagnostic : memoire accumulee
    Desocclusion,  // diagnostic : zones decouvertes
    Mouvement,     // vecteurs de mouvement du "jeu"
    UnivReactivite,  // diagnostic universel : image refaite a neuf
    UnivMemoire,     // diagnostic universel : memoire accumulee
    UnivFlot,        // diagnostic universel : doute du flot estime
    Count
};

const char* ViewName(View v);
// Valeur de LABO_VIEW_* du shader de composition.
uint32_t ComposeMode(View v);
// La vue a-t-elle besoin de la sortie diagnostic de USR ?
bool NeedsDebug(View v);
// La vue a-t-elle besoin de USR Universel (image ou diagnostic) ?
bool NeedsUniversal(View v);
// ... et de sa sortie diagnostic ?
bool NeedsUniversalDebug(View v);

enum class Quality : uint32_t {
    Native,       // 1.0x
    Quality,      // 1.5x
    Balanced,     // 1.7x
    Performance,  // 2.0x
    Ultra,        // 3.0x
    Custom,       // rapport libre
    Count
};

const char* QualityName(Quality q);

struct Settings {
    // Image
    Quality quality = Quality::Performance;
    float customRatio = 2.5f;       // 1.0 .. 4.0
    float sharpness = 0.0f;         // 0 .. 1
    bool jitter = true;
    uint32_t jitterPhases = 0;      // 0 = automatique
    // IA
    bool network = true;
    uint32_t model = 1;             // 0 stable, 1 equilibre, 2 detail
    float networkStrength = 1.0f;   // 0 .. 3
    // Accumulation
    float historyLength = 10.0f;    // 1 .. 64 images
    float antiGhosting = 1.25f;     // 0.25 .. 8 ecarts-types
    float kernelWidth = 1.0f;       // 0.25 .. 4
    // USR Universel : 1 = l'image finale seule (emulateur sans retouche
    // du jeu), 2 = jitter injecte dans le rendu (grille 2x2 / 3x3)
    uint32_t universalLevel = 2;
    // Comparaison
    View left = View::UsrIA;
    View right = View::Verite;
    float split = 0.5f;             // 0 .. 1 (1 = gauche seule)
    uint32_t zoom = 0;              // 0, 2, 4 ou 8
    float zoomX = 0.62f;            // centre de la loupe (fraction d'ecran)
    float zoomY = 0.42f;
    // Scene
    bool cameraMoving = true;
    bool objectsMoving = true;
    float sceneSpeed = 1.0f;        // 0.1 .. 4
    bool paused = false;
    uint32_t truthSamples = 4;      // 1 .. 4 par axe
    // Affichage
    bool showMenu = true;
    bool showStats = true;
};

const char* ModelName(uint32_t model);
const char* UniversalLevelName(uint32_t level);
// Anti-fantomes de USR Universel (sortie de boite, defaut 0,3) : meme
// reglage que celui de USR, rapporte a sa valeur par defaut (1,25).
float UniversalAntiGhosting(const Settings& s);

float UpscaleRatio(const Settings& s);
void RenderSize(const Settings& s, uint32_t displayW, uint32_t displayH,
                uint32_t* renderW, uint32_t* renderH);
uint32_t JitterPhases(const Settings& s, uint32_t renderW, uint32_t displayW);
// Meme suite que usr::GetJitterOffset (Halton 2, 3) ; (0, 0) si le jitter
// est coupe.
void JitterOffset(const Settings& s, uint32_t frame, uint32_t phases,
                  float* x, float* y);

// --- Scene : contenu exact du cbuffer LaboScene --------------------------

struct SceneObjectGpu {
    float centers[4];  // xy courant, zw precedent
    float shape[4];    // rayon, profondeur, anneaux, 0 disque / 1 boite
    float tint[4];
};

struct SceneConstants {
    float camera[4];   // xy courant, zw precedent
    float aspect;
    float screenPhase;
    uint32_t neonOn;
    uint32_t objectCount;
    SceneObjectGpu objects[8];
};
static_assert(sizeof(SceneConstants) == 32 + 8 * 48, "cbuffer LaboScene");

// Instants de la scene : la camera, les objets et les animations
// (ecran, neon) avancent separement, pour pouvoir figer l'un ou l'autre.
struct SceneTimes {
    double camera = 0.0;
    double objects = 0.0;
    double anim = 0.0;
};

void FillSceneConstants(const SceneTimes& now, const SceneTimes& prev,
                        SceneConstants* out);

// --- Manette ------------------------------------------------------------

struct PadState {
    bool up = false, down = false, left = false, right = false;
    bool a = false, b = false, x = false, y = false;
    bool lb = false, rb = false, menu = false, view = false;
    bool rstick = false;
    float lx = 0, ly = 0, rx = 0, ry = 0;  // -1 .. 1, y vers le haut
    float lt = 0, rt = 0;                  // 0 .. 1
};

// --- Mesures affichees ---------------------------------------------------

enum Pass : uint32_t {
    kPassScene,
    kPassUsrIA,
    kPassUsrSansIA,
    kPassUsrUniversel,
    kPassVerite,
    kPassComparaisons,
    kPassComposition,
    kPassCount
};

struct Stats {
    double fps = 0.0;
    double gpuMs[kPassCount] = {};
    double gpuTotalMs = 0.0;
    uint32_t renderW = 0, renderH = 0;
    uint32_t displayW = 0, displayH = 0;
    uint32_t jitterPhases = 0;
    uint32_t universalPeriod = 0;   // periode du jitter injecte (niveau 2)
    std::string device;
};

// --- Le controleur -------------------------------------------------------

class Controller {
public:
    Controller();

    Settings& settings() { return settings_; }
    const Settings& settings() const { return settings_; }

    // A appeler une fois par image avec l'etat de la manette.
    void Update(const PadState& pad, double dt);

    // Evenements a consommer par le moteur de rendu.
    bool TakeHistoryReset();   // effacer l'historique des deux USR
    SceneTimes sceneNow() const { return now_; }
    SceneTimes scenePrev() const { return prev_; }

    // Remplit la grille de texte (menu, mesures, etiquettes).
    void BuildOverlay(TextGrid& grid, const Stats& stats) const;

    // Menu : pour les tests et l'aide.
    uint32_t pageCount() const;
    uint32_t page() const { return page_; }
    uint32_t selected() const { return selected_; }
    std::string PageTitle(uint32_t page) const;
    uint32_t ItemCount(uint32_t page) const;
    std::string ItemLabel(uint32_t page, uint32_t item) const;
    std::string ItemValue(uint32_t page, uint32_t item) const;

    // Avance la scene d'une image (appele par Update, expose pour les tests).
    void StepScene();

    // Preregalages (menu "Prereglages").
    static uint32_t PresetCount();
    static const char* PresetName(uint32_t i);
    void ApplyPreset(uint32_t i);

private:
    struct Item;
    std::vector<Item> Items(uint32_t page) const;
    void Adjust(int dir);
    void Activate();

    struct Repeat {
        bool held = false;
        double timer = 0.0;
        double heldFor = 0.0;
    };
    bool Pulse(Repeat& r, bool down, double dt);

    Settings settings_;
    SceneTimes now_, prev_;
    uint32_t page_ = 0;
    uint32_t selected_ = 0;
    bool resetHistory_ = true;
    PadState last_;
    Repeat up_, down_, left_, right_;
};

} // namespace labo
