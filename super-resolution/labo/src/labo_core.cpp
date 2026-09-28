#include "labo_core.h"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <functional>

#include "labo_scene_params.h"

namespace labo {

namespace {

float Clampf(float v, float lo, float hi)
{
    return v < lo ? lo : (v > hi ? hi : v);
}

// Nombres a la francaise : virgule decimale.
std::string Fixed(double v, int decimals)
{
    char buf[48];
    std::snprintf(buf, sizeof(buf), "%.*f", decimals, v);
    std::string s(buf);
    std::replace(s.begin(), s.end(), '.', ',');
    return s;
}

std::string Percent(float v)
{
    return std::to_string(static_cast<int>(std::lround(v * 100.0f))) + " %";
}

std::string OnOff(bool v, const char* on = "Activé", const char* off = "Coupé")
{
    return v ? on : off;
}

template <typename E>
E Cycle(E v, int dir, uint32_t count)
{
    const int n = static_cast<int>(count);
    const int i = (static_cast<int>(v) + dir % n + n) % n;
    return static_cast<E>(i);
}

float Step(float v, int dir, float step, float lo, float hi)
{
    // arrondi au pas, pour ne pas accumuler 0,30000001
    const float r = std::round((v + dir * step) / step) * step;
    return Clampf(r, lo, hi);
}

float StepFactor(float v, int dir, float factor, float lo, float hi)
{
    const float r = dir > 0 ? v * factor : v / factor;
    return Clampf(std::round(r * 100.0f) / 100.0f, lo, hi);
}

double Halton(uint32_t index, uint32_t base)
{
    double f = 1.0, r = 0.0;
    while (index > 0) {
        f /= base;
        r += f * (index % base);
        index /= base;
    }
    return r;
}

std::vector<std::string> Wrap(const std::string& text, uint32_t width)
{
    std::vector<std::string> lines;
    std::string line, word;
    auto flush_word = [&]() {
        if (word.empty())
            return;
        const uint32_t need = Utf8Length(line) + (line.empty() ? 0 : 1) +
                              Utf8Length(word);
        if (!line.empty() && need > width) {
            lines.push_back(line);
            line.clear();
        }
        line += (line.empty() ? "" : " ") + word;
        word.clear();
    };
    for (char c : text) {
        if (c == ' ')
            flush_word();
        else
            word += c;
    }
    flush_word();
    if (!line.empty())
        lines.push_back(line);
    return lines;
}

} // namespace

// --------------------------------------------------------------------------
// Noms
// --------------------------------------------------------------------------

const char* ViewName(View v)
{
    switch (v) {
    case View::UsrIA: return "USR + IA";
    case View::UsrSansIA: return "USR sans IA";
    case View::UsrUniversel: return "USR Universel (sans vecteurs)";
    case View::Bilineaire: return "Bilinéaire";
    case View::Verite: return "Vérité terrain";
    case View::EntreeBrute: return "Entrée brute";
    case View::Alpha: return "Diag. : alpha";
    case View::Beta: return "Diag. : bêta";
    case View::Confiance: return "Diag. : confiance";
    case View::Desocclusion: return "Diag. : désocclusion";
    case View::Mouvement: return "Mouvement";
    case View::UnivReactivite: return "Diag. univ. : réactivité";
    case View::UnivMemoire: return "Diag. univ. : mémoire";
    case View::UnivFlot: return "Diag. univ. : doute du flot";
    default: return "?";
    }
}

uint32_t ComposeMode(View v)
{
    switch (v) {
    case View::Alpha: return 1;
    case View::Beta: return 2;
    case View::Confiance: return 3;
    case View::Desocclusion: return 4;
    case View::Mouvement: return 5;
    case View::UsrUniversel: return 6;    // deja compressee pour l'ecran
    case View::UnivReactivite: return 7;  // canal r de la texture de la vue
    case View::UnivMemoire: return 9;     // canal b
    case View::UnivFlot: return 10;       // canal a
    default: return 0;
    }
}

bool NeedsDebug(View v)
{
    return v == View::Alpha || v == View::Beta || v == View::Confiance ||
           v == View::Desocclusion;
}

bool NeedsUniversal(View v)
{
    return v == View::UsrUniversel || NeedsUniversalDebug(v);
}

bool NeedsUniversalDebug(View v)
{
    return v == View::UnivReactivite || v == View::UnivMemoire ||
           v == View::UnivFlot;
}

const char* QualityName(Quality q)
{
    switch (q) {
    case Quality::Native: return "Natif 1,0x";
    case Quality::Quality: return "Qualité 1,5x";
    case Quality::Balanced: return "Équilibré 1,7x";
    case Quality::Performance: return "Performance 2,0x";
    case Quality::Ultra: return "Ultra 3,0x";
    case Quality::Custom: return "Personnalisé";
    default: return "?";
    }
}

const char* ModelName(uint32_t model)
{
    switch (model) {
    case 0: return "Stable";
    case 1: return "Équilibré";
    case 2: return "Détail";
    default: return "?";
    }
}

const char* UniversalLevelName(uint32_t level)
{
    return level >= 2 ? "2 : jitter injecté" : "1 : image seule";
}

float UniversalAntiGhosting(const Settings& s)
{
    return 0.3f * s.antiGhosting / 1.25f;
}

// --------------------------------------------------------------------------
// Tailles, jitter
// --------------------------------------------------------------------------

float UpscaleRatio(const Settings& s)
{
    switch (s.quality) {
    case Quality::Native: return 1.0f;
    case Quality::Quality: return 1.5f;
    case Quality::Balanced: return 1.7f;
    case Quality::Performance: return 2.0f;
    case Quality::Ultra: return 3.0f;
    case Quality::Custom: return Clampf(s.customRatio, 1.0f, 4.0f);
    default: return 2.0f;
    }
}

void RenderSize(const Settings& s, uint32_t displayW, uint32_t displayH,
                uint32_t* renderW, uint32_t* renderH)
{
    const double ratio = UpscaleRatio(s);
    const auto scale = [ratio](uint32_t v) {
        const long r = std::lround(static_cast<double>(v) / ratio);
        return static_cast<uint32_t>(std::max(16L, r));
    };
    *renderW = std::min(scale(displayW), displayW);
    *renderH = std::min(scale(displayH), displayH);
}

uint32_t JitterPhases(const Settings& s, uint32_t renderW, uint32_t displayW)
{
    if (s.jitterPhases != 0)
        return s.jitterPhases;
    const double ratio = static_cast<double>(displayW) /
                         static_cast<double>(std::max(renderW, 1u));
    return std::max(8u, static_cast<uint32_t>(std::ceil(8.0 * ratio * ratio)));
}

void JitterOffset(const Settings& s, uint32_t frame, uint32_t phases, float* x,
                  float* y)
{
    if (!s.jitter) {
        *x = *y = 0.0f;
        return;
    }
    const uint32_t k = frame % std::max(phases, 1u) + 1;
    *x = static_cast<float>(Halton(k, 2) - 0.5);
    *y = static_cast<float>(Halton(k, 3) - 0.5);
}

// --------------------------------------------------------------------------
// Scene
// --------------------------------------------------------------------------

void FillSceneConstants(const SceneTimes& now, const SceneTimes& prev,
                        SceneConstants* out)
{
    using namespace scene;
    const auto camera = [](double t, double* c) {
        c[0] = kCam0[0] + kCameraSpeed[0] * t + kWobble * std::sin(0.13 * t);
        c[1] = kCam0[1] + kCameraSpeed[1] * t + kWobble * std::cos(0.09 * t);
    };
    const auto center = [](const ObjectParams& o, double t, double* c) {
        for (int k = 0; k < 2; ++k)
            c[k] = o.base[k] + o.amp[k] * std::sin(o.freq[k] * t + o.phase[k]);
    };

    *out = SceneConstants{};
    double c[2], cp[2];
    camera(now.camera, c);
    camera(prev.camera, cp);
    out->camera[0] = static_cast<float>(c[0]);
    out->camera[1] = static_cast<float>(c[1]);
    out->camera[2] = static_cast<float>(cp[0]);
    out->camera[3] = static_cast<float>(cp[1]);
    out->aspect = static_cast<float>(kAspect);
    const double phase = 0.09 * now.anim;
    out->screenPhase = static_cast<float>(phase - std::floor(phase));
    const long long seventh = static_cast<long long>(std::floor(now.anim / 7.0));
    out->neonOn = ((seventh % 2) + 2) % 2 == 0 ? 1u : 0u;

    // du plus loin au plus proche, comme Scene.shade
    uint32_t order[8];
    const uint32_t n = std::min<uint32_t>(kObjectCount, 8u);
    for (uint32_t i = 0; i < n; ++i)
        order[i] = i;
    std::stable_sort(order, order + n, [](uint32_t a, uint32_t b) {
        return kObjects[a].depth > kObjects[b].depth;
    });
    out->objectCount = n;
    for (uint32_t i = 0; i < n; ++i) {
        const ObjectParams& o = kObjects[order[i]];
        SceneObjectGpu& g = out->objects[i];
        center(o, now.objects, c);
        center(o, prev.objects, cp);
        g.centers[0] = static_cast<float>(c[0]);
        g.centers[1] = static_cast<float>(c[1]);
        g.centers[2] = static_cast<float>(cp[0]);
        g.centers[3] = static_cast<float>(cp[1]);
        g.shape[0] = static_cast<float>(o.radius);
        g.shape[1] = static_cast<float>(o.depth);
        g.shape[2] = static_cast<float>(o.rings);
        g.shape[3] = o.box ? 1.0f : 0.0f;
        for (int k = 0; k < 3; ++k)
            g.tint[k] = static_cast<float>(o.tint[k]);
    }
}

// --------------------------------------------------------------------------
// Menu
// --------------------------------------------------------------------------

struct Controller::Item {
    std::string label;
    std::string value;   // vide : action
    std::string help;
    std::function<void(Settings&, int)> adjust;   // gauche / droite
    std::function<void(Controller&)> activate;    // bouton A
};

namespace {

const char* const kPageTitles[] = {
    "Image", "IA", "Accumulation", "Universel", "Comparaison", "Scène",
    "Préréglages", "Aide",
};
constexpr uint32_t kPageCount = sizeof(kPageTitles) / sizeof(kPageTitles[0]);

struct Preset {
    const char* name;
    const char* help;
    void (*apply)(Settings&);
};

void KeepDisplay(Settings& s, const Settings& before)
{
    s.left = before.left;
    s.right = before.right;
    s.split = before.split;
    s.zoom = before.zoom;
    s.zoomX = before.zoomX;
    s.zoomY = before.zoomY;
    s.showMenu = before.showMenu;
    s.universalLevel = before.universalLevel;
    s.showStats = before.showStats;
    s.cameraMoving = before.cameraMoving;
    s.objectsMoving = before.objectsMoving;
    s.sceneSpeed = before.sceneSpeed;
    s.paused = before.paused;
    s.truthSamples = before.truthSamples;
}

const Preset kPresets[] = {
    {"Par défaut", "Les réglages avec lesquels le réseau a été entraîné.",
     [](Settings& s) { const Settings b = s; s = Settings{}; KeepDisplay(s, b); }},
    {"Qualité maximale",
     "Rendu en 1,5x, mémoire longue, un peu de netteté : le plus beau.",
     [](Settings& s) {
         const Settings b = s; s = Settings{}; KeepDisplay(s, b);
         s.quality = Quality::Quality; s.historyLength = 16.0f;
         s.sharpness = 0.2f;
     }},
    {"Performance maximale",
     "Rendu en 3x (9 fois moins de pixels calculés), modèle Stable.",
     [](Settings& s) {
         const Settings b = s; s = Settings{}; KeepDisplay(s, b);
         s.quality = Quality::Ultra; s.model = 0; s.sharpness = 0.3f;
     }},
    {"IA à fond (300 %)",
     "Puissance de l'IA triplée, modèle Détail, mémoire 32 images. "
     "Expérimental : plus de finesse, plus d'artefacts possibles.",
     [](Settings& s) {
         const Settings b = s; s = Settings{}; KeepDisplay(s, b);
         s.networkStrength = 3.0f; s.model = 2; s.historyLength = 32.0f;
     }},
    {"Sans IA (TAA classique)",
     "Le réseau est coupé : seule reste la règle fixe des TAA classiques.",
     [](Settings& s) {
         const Settings b = s; s = Settings{}; KeepDisplay(s, b);
         s.network = false;
     }},
    {"Sans jitter",
     "Sans décalage sous-pixel, l'accumulation n'apprend plus rien de "
     "nouveau : la super-résolution disparaît.",
     [](Settings& s) {
         const Settings b = s; s = Settings{}; KeepDisplay(s, b);
         s.jitter = false;
     }},
    {"Comparer IA / sans IA",
     "À gauche USR avec le réseau, à droite sans : la différence est "
     "surtout visible sur les lignes fines.",
     [](Settings& s) {
         s.left = View::UsrIA; s.right = View::UsrSansIA; s.split = 0.5f;
     }},
    {"Voir ce que décide l'IA",
     "À droite, la carte alpha : clair = l'IA fait confiance à l'image "
     "courante, sombre = à l'historique.",
     [](Settings& s) {
         s.left = View::UsrIA; s.right = View::Alpha; s.split = 0.5f;
     }},
    {"Avec / sans vecteurs",
     "À gauche USR, qui reçoit du jeu la profondeur et les vecteurs de "
     "mouvement ; à droite USR Universel, qui n'a que l'image (émulateur).",
     [](Settings& s) {
         s.left = View::UsrIA; s.right = View::UsrUniversel; s.split = 0.5f;
     }},
};
constexpr uint32_t kPresetCount = sizeof(kPresets) / sizeof(kPresets[0]);

} // namespace

uint32_t Controller::PresetCount() { return kPresetCount; }
const char* Controller::PresetName(uint32_t i)
{
    return i < kPresetCount ? kPresets[i].name : "?";
}

void Controller::ApplyPreset(uint32_t i)
{
    if (i >= kPresetCount)
        return;
    kPresets[i].apply(settings_);
    resetHistory_ = true;
}

Controller::Controller() = default;

uint32_t Controller::pageCount() const { return kPageCount; }

std::string Controller::PageTitle(uint32_t page) const
{
    return page < kPageCount ? kPageTitles[page] : "?";
}

std::vector<Controller::Item> Controller::Items(uint32_t page) const
{
    const Settings& s = settings_;
    std::vector<Item> it;
    auto add = [&](std::string label, std::string value, std::string help,
                   std::function<void(Settings&, int)> adjust,
                   std::function<void(Controller&)> activate = nullptr) {
        it.push_back({std::move(label), std::move(value), std::move(help),
                      std::move(adjust), std::move(activate)});
    };
    auto toggle = [](bool Settings::*field) {
        return [field](Settings& st, int) { st.*field = !(st.*field); };
    };

    switch (page) {
    case 0:  // Image
        add("Mode d'agrandissement", QualityName(s.quality),
            "Rapport entre l'image affichée et l'image calculée. "
            "Performance : 4 fois moins de pixels calculés.",
            [](Settings& st, int d) {
                st.quality = Cycle(st.quality, d,
                                   static_cast<uint32_t>(Quality::Count));
            });
        add("Rapport personnalisé", Fixed(s.customRatio, 1) + "x",
            "Rapport libre, de 1,0x à 4,0x. Actif en mode Personnalisé.",
            [](Settings& st, int d) {
                st.customRatio = Step(st.customRatio, d, 0.1f, 1.0f, 4.0f);
                st.quality = Quality::Custom;
            });
        add("Netteté", Percent(s.sharpness),
            "Accentuation finale. Trop forte : contours durs, bruit visible.",
            [](Settings& st, int d) {
                st.sharpness = Step(st.sharpness, d, 0.05f, 0.0f, 1.0f);
            });
        add("Jitter", OnOff(s.jitter),
            "Décalage sous-pixel à chaque image : c'est lui qui apporte les "
            "détails. Coupez-le pour voir la super-résolution disparaître.",
            toggle(&Settings::jitter));
        add("Phases de jitter",
            s.jitterPhases ? std::to_string(s.jitterPhases) : "Auto",
            "Positions de jitter avant de recommencer. Auto : 8 fois le "
            "rapport au carré.",
            [](Settings& st, int d) {
                static const uint32_t kSteps[] = {0, 4, 8, 16, 32, 64, 128};
                int i = 0;
                while (i < 6 && kSteps[i] != st.jitterPhases) ++i;
                i = std::max(0, std::min(6, i + d));
                st.jitterPhases = kSteps[i];
            });
        break;
    case 1:  // IA
        add("IA (réseau de neurones)", OnOff(s.network),
            "Le réseau décide pixel par pixel quoi garder du passé. Coupé : "
            "règle fixe, comme un TAA classique.",
            toggle(&Settings::network));
        add("Modèle", ModelName(s.model),
            "Stable : scintille le moins. Équilibré : réglage d'origine. "
            "Détail : le plus fin, un peu moins stable.",
            [](Settings& st, int d) { st.model = (st.model + 3 + d) % 3; });
        add("Puissance de l'IA", Percent(s.networkStrength),
            "Dose l'influence du réseau. 0 % = sans IA, 100 % = tel "
            "qu'entraîné, au-delà = décisions amplifiées (expérimental).",
            [](Settings& st, int d) {
                st.networkStrength =
                    Step(st.networkStrength, d, 0.1f, 0.0f, 3.0f);
            });
        break;
    case 2:  // Accumulation
        add("Mémoire (images)", std::to_string(std::lround(s.historyLength)),
            "Images accumulées au maximum. Plus : plus fin à l'arrêt, mais "
            "oublie plus lentement (traînées).",
            [](Settings& st, int d) {
                st.historyLength = Step(st.historyLength, d, 1.0f, 1.0f, 64.0f);
            });
        add("Anti-fantômes", Fixed(s.antiGhosting, 2),
            "Tolérance envers l'historique. Petit : moins de traînées mais "
            "plus de scintillement. Grand : plus de détail, plus de traînées.",
            [](Settings& st, int d) {
                st.antiGhosting =
                    StepFactor(st.antiGhosting, d, 1.1f, 0.25f, 8.0f);
            });
        add("Finesse du noyau", Percent(s.kernelWidth),
            "Largeur du filtre d'accumulation. Moins de 100 % : plus net mais "
            "bruité. Plus de 100 % : plus doux.",
            [](Settings& st, int d) {
                st.kernelWidth = StepFactor(st.kernelWidth, d, 1.08f, 0.25f,
                                            4.0f);
            });
        add("Effacer l'historique", "",
            "Oublie tout, comme lors d'un changement de plan. (Bouton X.)",
            nullptr, [](Controller& c) { c.resetHistory_ = true; });
        break;
    case 3:  // Universel
        add("Niveau", UniversalLevelName(s.universalLevel),
            "1 : USR Universel ne reçoit que l'image finale, comme un "
            "émulateur qui ne touche pas au jeu. 2 : l'émulateur décale "
            "lui-même le rendu (grille 2x2 ou 3x3) : bien plus de détails.",
            [](Settings& st, int) {
                st.universalLevel = st.universalLevel >= 2 ? 1 : 2;
            });
        add("Comparer avec / sans vecteurs", "",
            "À gauche USR (vecteurs de mouvement fournis par le jeu), à "
            "droite USR Universel (mouvement estimé sur l'image seule). "
            "Netteté, IA, mémoire et anti-fantômes s'appliquent aux deux.",
            nullptr, [](Controller& c) {
                c.settings_.left = View::UsrIA;
                c.settings_.right = View::UsrUniversel;
                c.settings_.split = 0.5f;
            });
        add("Comparer à la vérité", "",
            "À gauche USR Universel, à droite l'image calculée directement "
            "à la résolution de l'écran.",
            nullptr, [](Controller& c) {
                c.settings_.left = View::UsrUniversel;
                c.settings_.right = View::Verite;
                c.settings_.split = 0.5f;
            });
        add("Voir ce que décide l'IA", "",
            "À droite, la réactivité : clair = pixel refait à neuf (image "
            "courante), sombre = historique gardé.",
            nullptr, [](Controller& c) {
                c.settings_.left = View::UsrUniversel;
                c.settings_.right = View::UnivReactivite;
                c.settings_.split = 0.5f;
            });
        break;
    case 4:  // Comparaison
        add("Moitié gauche", ViewName(s.left),
            "Ce qu'affiche la partie gauche de l'écran. (Croix ↑↓ menu fermé.)",
            [](Settings& st, int d) {
                st.left = Cycle(st.left, d, static_cast<uint32_t>(View::Count));
            });
        add("Moitié droite", ViewName(s.right),
            "Ce qu'affiche la partie droite. (Croix ←→ menu fermé.)",
            [](Settings& st, int d) {
                st.right = Cycle(st.right, d,
                                 static_cast<uint32_t>(View::Count));
            });
        add("Séparation", Percent(s.split),
            "Position de la ligne de séparation. 100 % : gauche seule. "
            "(Gâchettes LT / RT.)",
            [](Settings& st, int d) {
                st.split = Step(st.split, d, 0.02f, 0.0f, 1.0f);
            });
        add("Loupe", s.zoom ? "x" + std::to_string(s.zoom) : "Coupée",
            "Grossit les pixels autour d'un point. Stick droit : déplacer ; "
            "clic du stick droit : changer le grossissement.",
            [](Settings& st, int d) {
                static const uint32_t kZoom[] = {0, 2, 4, 8};
                int i = 0;
                while (i < 3 && kZoom[i] != st.zoom) ++i;
                st.zoom = kZoom[(i + 4 + d) % 4];
            });
        break;
    case 5:  // Scene
        add("Caméra", OnOff(s.cameraMoving, "Mobile", "Fixe"),
            "Défilement du décor.", toggle(&Settings::cameraMoving));
        add("Objets", OnOff(s.objectsMoving, "Animés", "Fixes"),
            "Mouvement des objets au premier plan.",
            toggle(&Settings::objectsMoving));
        add("Vitesse", Percent(s.sceneSpeed),
            "Plus vite = plus difficile pour l'upscaler (moins d'images "
            "utiles dans l'historique).",
            [](Settings& st, int d) {
                st.sceneSpeed = Step(st.sceneSpeed, d, 0.1f, 0.1f, 4.0f);
            });
        add("Pause", OnOff(s.paused, "Oui", "Non"),
            "Fige la scène : l'image doit alors converger vers la vérité "
            "terrain.",
            toggle(&Settings::paused));
        add("Vérité terrain", std::to_string(s.truthSamples * s.truthSamples) +
                                  " éch./pixel",
            "Qualité de l'image de référence (coûteuse : ne sert qu'à "
            "comparer).",
            [](Settings& st, int d) {
                st.truthSamples = static_cast<uint32_t>(std::max(
                    1, std::min(4, static_cast<int>(st.truthSamples) + d)));
            });
        add("Revenir au début", "", "Remet la scène à son état initial.",
            nullptr, [](Controller& c) {
                c.now_ = SceneTimes{};
                c.prev_ = SceneTimes{};
                c.resetHistory_ = true;
            });
        break;
    case 6:  // Prereglages
        for (uint32_t i = 0; i < kPresetCount; ++i)
            add(kPresets[i].name, "", kPresets[i].help, nullptr,
                [i](Controller& c) { c.ApplyPreset(i); });
        break;
    default:
        break;
    }
    return it;
}

uint32_t Controller::ItemCount(uint32_t page) const
{
    return static_cast<uint32_t>(Items(page).size());
}

std::string Controller::ItemLabel(uint32_t page, uint32_t item) const
{
    const auto items = Items(page);
    return item < items.size() ? items[item].label : "";
}

std::string Controller::ItemValue(uint32_t page, uint32_t item) const
{
    const auto items = Items(page);
    return item < items.size() ? items[item].value : "";
}

void Controller::Adjust(int dir)
{
    const auto items = Items(page_);
    if (selected_ < items.size() && items[selected_].adjust)
        items[selected_].adjust(settings_, dir);
}

void Controller::Activate()
{
    const auto items = Items(page_);
    if (selected_ >= items.size())
        return;
    if (items[selected_].activate)
        items[selected_].activate(*this);
    else if (items[selected_].adjust)
        items[selected_].adjust(settings_, +1);
}

bool Controller::TakeHistoryReset()
{
    const bool r = resetHistory_;
    resetHistory_ = false;
    return r;
}

// Appui bref : une impulsion. Appui maintenu : repetition qui accelere.
bool Controller::Pulse(Repeat& r, bool down, double dt)
{
    if (!down) {
        r = Repeat{};
        return false;
    }
    if (!r.held) {
        r.held = true;
        r.timer = 0.35;
        return true;
    }
    r.heldFor += dt;
    r.timer -= dt;
    if (r.timer <= 0.0) {
        r.timer += r.heldFor > 1.5 ? 0.03 : 0.08;
        return true;
    }
    return false;
}

void Controller::StepScene()
{
    prev_ = now_;
    if (settings_.paused)
        return;
    const double speed = settings_.sceneSpeed;
    now_.anim += speed;
    if (settings_.cameraMoving)
        now_.camera += speed;
    if (settings_.objectsMoving)
        now_.objects += speed;
}

void Controller::Update(const PadState& pad, double dt)
{
    const PadState& was = last_;
    auto pressed = [](bool now, bool before) { return now && !before; };
    Settings& s = settings_;

    if (pressed(pad.menu, was.menu))
        s.showMenu = !s.showMenu;
    if (pressed(pad.view, was.view))
        s.showStats = !s.showStats;
    if (pressed(pad.x, was.x))
        resetHistory_ = true;
    if (pressed(pad.y, was.y))
        std::swap(s.left, s.right);
    if (pressed(pad.rstick, was.rstick)) {
        static const uint32_t kZoom[] = {0, 2, 4, 8};
        int i = 0;
        while (i < 3 && kZoom[i] != s.zoom) ++i;
        s.zoom = kZoom[(i + 1) % 4];
    }

    const bool up = pad.up || pad.ly > 0.6f;
    const bool down = pad.down || pad.ly < -0.6f;
    const bool left = pad.left || pad.lx < -0.6f;
    const bool right = pad.right || pad.lx > 0.6f;
    const bool pUp = Pulse(up_, up, dt);
    const bool pDown = Pulse(down_, down, dt);
    const bool pLeft = Pulse(left_, left, dt);
    const bool pRight = Pulse(right_, right, dt);

    if (s.showMenu) {
        if (pressed(pad.lb, was.lb) || pressed(pad.rb, was.rb)) {
            const int d = pad.rb ? 1 : -1;
            page_ = (page_ + kPageCount + d) % kPageCount;
            selected_ = 0;
        }
        const uint32_t n = ItemCount(page_);
        if (n > 0) {
            if (pUp)
                selected_ = (selected_ + n - 1) % n;
            if (pDown)
                selected_ = (selected_ + 1) % n;
            if (pLeft)
                Adjust(-1);
            if (pRight)
                Adjust(+1);
            if (pressed(pad.a, was.a))
                Activate();
        }
        if (pressed(pad.b, was.b))
            s.showMenu = false;
    } else {
        // menu ferme : la croix change les vues comparees
        if (pUp || pDown)
            s.left = Cycle(s.left, pUp ? -1 : 1,
                           static_cast<uint32_t>(View::Count));
        if (pLeft || pRight)
            s.right = Cycle(s.right, pLeft ? -1 : 1,
                            static_cast<uint32_t>(View::Count));
    }

    const float move = static_cast<float>(dt);
    s.split = Clampf(s.split + (pad.rt - pad.lt) * 0.5f * move, 0.0f, 1.0f);
    if (s.zoom) {
        s.zoomX = Clampf(s.zoomX + pad.rx * 0.35f * move, 0.0f, 1.0f);
        s.zoomY = Clampf(s.zoomY - pad.ry * 0.35f * move, 0.0f, 1.0f);
    }
    last_ = pad;
    StepScene();
}

// --------------------------------------------------------------------------
// Texte a l'ecran
// --------------------------------------------------------------------------

void Controller::BuildOverlay(TextGrid& grid, const Stats& stats) const
{
    grid.Clear();
    const Settings& s = settings_;
    const int cols = static_cast<int>(grid.cols());
    const int rows = static_cast<int>(grid.rows());

    // Etiquettes des deux moities
    if (s.split > 0.02f)
        grid.Print(1, rows - 2, std::string("◀ ") + ViewName(s.left), kYellow,
                   kCellPanel);
    if (s.split < 0.98f)
        grid.PrintRight(cols - 1, rows - 2,
                        std::string(ViewName(s.right)) + " ▶", kYellow,
                        kCellPanel);

    // Mesures (en haut a droite) ; sur un petit ecran, le menu passe avant.
    const int menuWidth = std::min(54, cols - 2);
    const bool statsFit = !s.showMenu || cols >= menuWidth + 2 + 38;
    if (s.showStats && statsFit) {
        const int w = 36;
        const int x = cols - w - 1;
        int y = 1;
        grid.AddFlags(x - 1, 0, w + 2, 7 + kPassCount, kCellPanel);
        grid.Print(x, y++, "USR Labo  " + stats.device, kCyan);
        grid.Print(x, y++, "Images/s : " + Fixed(stats.fps, 0), kWhite);
        grid.Print(x, y++,
                   std::to_string(stats.renderW) + "x" +
                       std::to_string(stats.renderH) + " → " +
                       std::to_string(stats.displayW) + "x" +
                       std::to_string(stats.displayH) + " (" +
                       Fixed(UpscaleRatio(s), 1) + "x)",
                   kWhite);
        grid.Print(x, y++, "Jitter : " + (s.jitter
                                               ? std::to_string(
                                                     stats.jitterPhases) +
                                                     " phases"
                                               : std::string("coupé")),
                   kWhite);
        grid.Print(x, y++, "Universel : niveau " +
                               std::to_string(s.universalLevel >= 2 ? 2 : 1) +
                               (s.universalLevel >= 2
                                    ? " (" + std::to_string(
                                                 stats.universalPeriod) +
                                          " phases)"
                                    : std::string(" (sans jitter)")),
                   kWhite);
        grid.Print(x, y, "GPU total", kYellow);
        grid.PrintRight(x + w, y++, Fixed(stats.gpuTotalMs, 2) + " ms",
                        kYellow);
        static const char* const kNames[kPassCount] = {
            "  scène (jeu)", "  USR + IA", "  USR sans IA", "  USR Universel",
            "  vérité terrain", "  comparaisons", "  affichage"};
        for (uint32_t p = 0; p < kPassCount; ++p) {
            grid.Print(x, y, kNames[p], kGray);
            grid.PrintRight(x + w, y++, Fixed(stats.gpuMs[p], 2) + " ms",
                            kGray);
        }
    }

    // Menu (a gauche)
    if (!s.showMenu) {
        grid.Print(1, 1, "Menu : réglages   Vue : mesures", kGray, kCellPanel);
        return;
    }
    const int w = menuWidth;
    const int x = 1;
    int y = 1;
    const auto items = Items(page_);
    const int height = 3 + std::max(static_cast<int>(items.size()), 1) + 9;
    grid.AddFlags(0, 0, w + 2, height, kCellPanel);

    grid.Print(x, y, "USR LABO", kYellow);
    grid.PrintRight(x + w, y++, "LB ◀ " + PageTitle(page_) + " ▶ RB  " +
                                    std::to_string(page_ + 1) + "/" +
                                    std::to_string(kPageCount),
                    kCyan);
    ++y;

    if (page_ == kPageCount - 1) {  // Aide
        static const char* const kHelp[] = {
            "Croix / stick G   choisir, régler",
            "LB / RB           changer de page",
            "A                 valider   B  fermer",
            "Menu              menu      Vue  mesures",
            "X                 effacer l'historique",
            "Y                 échanger gauche / droite",
            "LT / RT           déplacer la séparation",
            "Stick droit       déplacer la loupe",
            "Clic stick droit  grossissement de la loupe",
            "Menu fermé : croix ↑↓ vue gauche, ←→ vue droite",
        };
        for (const char* line : kHelp)
            grid.Print(x, y++, line, kWhite);
        return;
    }

    for (uint32_t i = 0; i < items.size(); ++i) {
        const Item& item = items[i];
        const bool sel = i == selected_;
        if (sel)
            grid.AddFlags(x - 1, y, w + 2, 1, kCellHighlight);
        grid.Print(x, y, std::string(sel ? "► " : "  ") + item.label,
                   sel ? kYellow : kWhite);
        if (!item.value.empty())
            grid.PrintRight(x + w, y,
                            item.adjust ? "◀ " + item.value + " ▶" : item.value,
                            kCyan);
        else if (item.activate)
            grid.PrintRight(x + w, y, "[A]", kGreen);
        ++y;
    }
    ++y;
    if (selected_ < items.size()) {
        for (const std::string& line : Wrap(items[selected_].help,
                                            static_cast<uint32_t>(w)))
            grid.Print(x, y++, line, kGray);
    }
    grid.Print(x, height - 2, "A valider  B fermer  X effacer  Y échanger",
               kGray);
}

} // namespace labo
