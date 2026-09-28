// Tests du coeur du Labo (reglages, menu, texte, scene), sans GPU.
//   g++ -std=c++17 -I labo/src labo/src/labo_core.cpp labo/src/labo_text.cpp
//       labo/tests/test_labo_core.cpp -o test_labo_core && ./test_labo_core
// Avec --scene t1 t2 ... : ecrit les constantes de scene (une ligne par
// instant) pour comparaison avec la reference Python.

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>

#include "labo_core.h"
#include "labo_text.h"

using namespace labo;

static int g_failures = 0;
static int g_checks = 0;

#define CHECK(cond)                                                        \
    do {                                                                   \
        ++g_checks;                                                        \
        if (!(cond)) {                                                     \
            ++g_failures;                                                  \
            std::printf("ECHEC %s:%d : %s\n", __FILE__, __LINE__, #cond); \
        }                                                                  \
    } while (0)

static std::string RowText(const TextGrid& g, uint32_t row)
{
    // Reconstitue les caracteres ASCII d'une ligne (indice glyphe -> code).
    std::string s;
    for (uint32_t c = 0; c < g.cols(); ++c) {
        const uint32_t glyph = g.At(c, row) & kCellGlyphMask;
        char ch = ' ';
        for (uint32_t cp = 33; cp < 127; ++cp)
            if (GlyphIndex(cp) == glyph && glyph != 0)
                ch = static_cast<char>(cp);
        s += ch;
    }
    return s;
}

static bool GridContains(const TextGrid& g, const char* needle)
{
    for (uint32_t r = 0; r < g.rows(); ++r)
        if (RowText(g, r).find(needle) != std::string::npos)
            return true;
    return false;
}

static void TestUtf8()
{
    size_t pos = 0;
    const std::string e = "é◀A";
    CHECK(DecodeUtf8(e, &pos) == 0xE9 && pos == 2);
    CHECK(DecodeUtf8(e, &pos) == 0x25C0 && pos == 5);
    CHECK(DecodeUtf8(e, &pos) == 'A' && pos == 6);
    pos = 0;
    const std::string bad = "\xFF" "a";
    CHECK(DecodeUtf8(bad, &pos) == 0xFFFD && pos == 1);
    CHECK(Utf8Length("Réglé ▶") == 7);
}

static void TestGrid()
{
    CHECK(GlyphIndex(' ') == 0);
    CHECK(GlyphIndex('A') != 0 && GlyphIndex('A') != GlyphIndex('?'));
    CHECK(GlyphIndex(0x4E2D) == GlyphIndex('?'));  // absent : '?'
    TextGrid g;
    g.Resize(20, 3);
    const int end = g.Print(2, 1, "Salut", kYellow);
    CHECK(end == 7);
    CHECK((g.At(2, 1) & kCellGlyphMask) == GlyphIndex('S'));
    CHECK(((g.At(2, 1) >> kCellColorShift) & 7u) == kYellow);
    g.PrintRight(20, 2, "fin", kWhite);
    CHECK((g.At(19, 2) & kCellGlyphMask) == GlyphIndex('n'));
    g.AddFlags(0, 0, 4, 1, kCellPanel);
    CHECK((g.At(3, 0) & kCellPanel) != 0 && (g.At(4, 0) & kCellPanel) == 0);
    g.Print(-3, 0, "abcdef", kWhite);  // coupe a gauche sans deborder
    CHECK((g.At(0, 0) & kCellGlyphMask) == GlyphIndex('d'));
    CHECK((g.At(0, 0) & kCellPanel) != 0);  // le panneau est conserve
}

static void TestSizes()
{
    Settings s;
    uint32_t w, h;
    s.quality = Quality::Performance;
    RenderSize(s, 3840, 2160, &w, &h);
    CHECK(w == 1920 && h == 1080);
    s.quality = Quality::Ultra;
    RenderSize(s, 3840, 2160, &w, &h);
    CHECK(w == 1280 && h == 720);
    s.quality = Quality::Native;
    RenderSize(s, 3840, 2160, &w, &h);
    CHECK(w == 3840 && h == 2160);
    s.quality = Quality::Custom;
    s.customRatio = 9.0f;  // borne a 4
    RenderSize(s, 3840, 2160, &w, &h);
    CHECK(w == 960 && h == 540);
    s.customRatio = 4.0f;
    RenderSize(s, 40, 30, &w, &h);  // minimum 16, jamais plus que l'ecran
    CHECK(w == 16 && h == 16);
    s.quality = Quality::Performance;
    CHECK(JitterPhases(s, 1920, 3840) == 32);
    CHECK(JitterPhases(s, 3840, 3840) == 8);
    s.jitterPhases = 64;
    CHECK(JitterPhases(s, 1920, 3840) == 64);
    float x, y;
    JitterOffset(s, 0, 32, &x, &y);
    CHECK(std::fabs(x - 0.0f) < 1e-6f && std::fabs(y + 1.0f / 6.0f) < 1e-6f);
    s.jitter = false;
    JitterOffset(s, 5, 32, &x, &y);
    CHECK(x == 0.0f && y == 0.0f);
}

static PadState Pad() { return PadState{}; }

static void TestMenu()
{
    Controller c;
    CHECK(c.pageCount() == 8);
    CHECK(c.PageTitle(1) == "IA");
    CHECK(c.TakeHistoryReset());   // la premiere image repart de zero
    CHECK(!c.TakeHistoryReset());

    PadState p = Pad();
    p.rb = true;
    c.Update(p, 1.0 / 60);
    c.Update(Pad(), 1.0 / 60);
    CHECK(c.page() == 1);           // page IA
    p = Pad();
    p.down = true;
    c.Update(p, 1.0 / 60);
    c.Update(Pad(), 1.0 / 60);
    p.down = true;
    c.Update(p, 1.0 / 60);
    c.Update(Pad(), 1.0 / 60);
    CHECK(c.selected() == 2);       // "Puissance de l'IA"
    CHECK(c.ItemValue(1, 2) == "100 %");
    p = Pad();
    p.right = true;
    c.Update(p, 1.0 / 60);          // un appui : +10 %
    c.Update(Pad(), 1.0 / 60);
    CHECK(c.ItemValue(1, 2) == "110 %");
    // maintenu 3 s : la repetition monte jusqu'a la borne (300 %)
    for (int i = 0; i < 180; ++i)
        c.Update(p, 1.0 / 60);
    c.Update(Pad(), 1.0 / 60);
    CHECK(std::fabs(c.settings().networkStrength - 3.0f) < 1e-5f);

    // B ferme le menu ; Menu le rouvre
    p = Pad();
    p.b = true;
    c.Update(p, 1.0 / 60);
    CHECK(!c.settings().showMenu);
    c.Update(Pad(), 1.0 / 60);
    p = Pad();
    p.menu = true;
    c.Update(p, 1.0 / 60);
    CHECK(c.settings().showMenu);
    c.Update(Pad(), 1.0 / 60);

    // X efface l'historique ; Y echange les vues
    const View l = c.settings().left, r = c.settings().right;
    p = Pad();
    p.x = true;
    p.y = true;
    c.Update(p, 1.0 / 60);
    CHECK(c.TakeHistoryReset());
    CHECK(c.settings().left == r && c.settings().right == l);
    c.Update(Pad(), 1.0 / 60);

    // gachettes : la separation bouge et reste bornee
    p = Pad();
    p.rt = 1.0f;
    for (int i = 0; i < 300; ++i)
        c.Update(p, 1.0 / 60);
    CHECK(c.settings().split == 1.0f);
}

static void TestPresets()
{
    Controller c;
    uint32_t fond = 0, defaut = 0, sansIA = 0;
    for (uint32_t i = 0; i < Controller::PresetCount(); ++i) {
        const std::string n = Controller::PresetName(i);
        if (n.find("fond") != std::string::npos) fond = i;
        if (n == "Par défaut") defaut = i;
        if (n.find("Sans IA") != std::string::npos) sansIA = i;
    }
    c.settings().left = View::Alpha;
    c.TakeHistoryReset();
    c.ApplyPreset(fond);
    CHECK(c.settings().networkStrength == 3.0f);
    CHECK(c.settings().model == 2);
    CHECK(c.settings().left == View::Alpha);   // la vue est conservee
    CHECK(c.TakeHistoryReset());
    c.ApplyPreset(sansIA);
    CHECK(!c.settings().network);
    c.ApplyPreset(defaut);
    CHECK(c.settings().network && c.settings().networkStrength == 1.0f);
    CHECK(c.settings().historyLength == 10.0f);
}

static void TestUniversal()
{
    // vues : noms, mode de composition, besoins
    CHECK(std::string(ViewName(View::UsrUniversel)) ==
          "USR Universel (sans vecteurs)");
    CHECK(ComposeMode(View::UsrUniversel) == 6);
    CHECK(ComposeMode(View::UnivReactivite) == 7);
    CHECK(ComposeMode(View::UnivMemoire) == 9);
    CHECK(ComposeMode(View::UnivFlot) == 10);
    CHECK(NeedsUniversal(View::UsrUniversel) && NeedsUniversal(View::UnivFlot));
    CHECK(!NeedsUniversal(View::UsrIA) && !NeedsUniversal(View::Alpha));
    CHECK(NeedsUniversalDebug(View::UnivMemoire));
    CHECK(!NeedsUniversalDebug(View::UsrUniversel));
    CHECK(!NeedsDebug(View::UnivReactivite));
    for (uint32_t v = 0; v < static_cast<uint32_t>(View::Count); ++v)
        CHECK(std::string(ViewName(static_cast<View>(v))) != "?");

    // anti-fantomes : meme reglage, rapporte au defaut de chaque mode
    Settings s;
    CHECK(std::fabs(UniversalAntiGhosting(s) - 0.3f) < 1e-6f);
    s.antiGhosting = 2.5f;
    CHECK(std::fabs(UniversalAntiGhosting(s) - 0.6f) < 1e-6f);

    // page Universel : le niveau bascule, les comparaisons se posent
    Controller c;
    uint32_t page = 0;
    while (page < c.pageCount() && c.PageTitle(page) != "Universel")
        ++page;
    CHECK(page == 3);
    CHECK(c.ItemLabel(page, 0) == "Niveau");
    CHECK(c.ItemValue(page, 0) == "2 : jitter injecté");
    for (uint32_t i = 0; i < page; ++i) {
        PadState p = Pad();
        p.rb = true;
        c.Update(p, 1.0 / 60);
        c.Update(Pad(), 1.0 / 60);
    }
    CHECK(c.page() == page);
    PadState p = Pad();
    p.right = true;
    c.Update(p, 1.0 / 60);
    c.Update(Pad(), 1.0 / 60);
    CHECK(c.settings().universalLevel == 1);
    CHECK(c.ItemValue(page, 0) == "1 : image seule");
    p = Pad();
    p.down = true;
    c.Update(p, 1.0 / 60);
    c.Update(Pad(), 1.0 / 60);
    p = Pad();
    p.a = true;
    c.Update(p, 1.0 / 60);
    c.Update(Pad(), 1.0 / 60);
    CHECK(c.settings().left == View::UsrIA);
    CHECK(c.settings().right == View::UsrUniversel);

    // le prereglage "Par defaut" garde le niveau choisi (reglage d'affichage)
    uint32_t defaut = 0, vecteurs = 0;
    for (uint32_t i = 0; i < Controller::PresetCount(); ++i) {
        const std::string n = Controller::PresetName(i);
        if (n == "Par défaut") defaut = i;
        if (n == "Avec / sans vecteurs") vecteurs = i;
    }
    CHECK(vecteurs != 0);
    c.ApplyPreset(defaut);
    CHECK(c.settings().universalLevel == 1);
    c.settings().right = View::Verite;
    c.ApplyPreset(vecteurs);
    CHECK(c.settings().right == View::UsrUniversel);

    // mesures : la ligne du mode universel s'affiche
    TextGrid g;
    g.Resize(160, 45);
    Stats st;
    st.universalPeriod = 4;
    c.settings().universalLevel = 2;
    c.BuildOverlay(g, st);
    CHECK(GridContains(g, "Universel : niveau 2 (4 phases)"));
    CHECK(GridContains(g, "USR Universel"));
}

static void TestSceneClock()
{
    Controller c;
    c.StepScene();
    CHECK(c.sceneNow().camera == 1.0 && c.scenePrev().camera == 0.0);
    c.settings().paused = true;
    c.StepScene();
    CHECK(c.sceneNow().anim == c.scenePrev().anim);  // pause : mouvement nul
    c.settings().paused = false;
    c.settings().objectsMoving = false;
    c.StepScene();
    CHECK(c.sceneNow().objects == c.scenePrev().objects);
    CHECK(c.sceneNow().camera == c.scenePrev().camera + 1.0);
    SceneConstants k;
    FillSceneConstants(c.sceneNow(), c.scenePrev(), &k);
    CHECK(k.objectCount == 4);
    for (uint32_t i = 1; i < k.objectCount; ++i)   // du plus loin au plus proche
        CHECK(k.objects[i - 1].shape[1] > k.objects[i].shape[1]);
    CHECK(k.screenPhase >= 0.0f && k.screenPhase < 1.0f);
}

static void TestOverlay()
{
    Controller c;
    TextGrid g;
    g.Resize(160, 45);
    Stats st;
    st.fps = 60;
    st.device = "Test";
    st.renderW = 1920; st.renderH = 1080; st.displayW = 3840; st.displayH = 2160;
    c.BuildOverlay(g, st);
    CHECK(GridContains(g, "USR LABO"));
    CHECK(GridContains(g, "USR Labo  Test"));
    CHECK(GridContains(g, "1920x1080"));
    // chaque page s'affiche sans deborder de la grille
    for (uint32_t page = 0; page < c.pageCount(); ++page) {
        PadState p = Pad();
        p.rb = true;
        c.Update(p, 0.016);
        c.Update(Pad(), 0.016);
        c.BuildOverlay(g, st);
        CHECK(GridContains(g, "USR LABO"));
    }
    // petite fenetre : rien ne plante
    g.Resize(40, 12);
    c.BuildOverlay(g, st);
    CHECK(g.cells().size() == 480);
}

static int DumpScene(int argc, char** argv)
{
    for (int i = 2; i < argc; ++i) {
        const double t = std::atof(argv[i]);
        SceneConstants k;
        FillSceneConstants(SceneTimes{t, t, t}, SceneTimes{t - 1, t - 1, t - 1},
                           &k);
        std::printf("%.9g %.9g %.9g %.9g %.9g %.9g %u %u", k.camera[0],
                    k.camera[1], k.camera[2], k.camera[3], k.aspect,
                    k.screenPhase, k.neonOn, k.objectCount);
        for (uint32_t o = 0; o < k.objectCount; ++o) {
            const SceneObjectGpu& g = k.objects[o];
            for (float v : g.centers) std::printf(" %.9g", v);
            for (float v : g.shape) std::printf(" %.9g", v);
            for (int j = 0; j < 3; ++j) std::printf(" %.9g", g.tint[j]);
        }
        std::printf("\n");
    }
    return 0;
}

int main(int argc, char** argv)
{
    if (argc > 1 && std::strcmp(argv[1], "--scene") == 0)
        return DumpScene(argc, argv);
    TestUtf8();
    TestGrid();
    TestSizes();
    TestMenu();
    TestPresets();
    TestUniversal();
    TestSceneClock();
    TestOverlay();
    std::printf("%d verifications, %d echec(s)\n", g_checks, g_failures);
    return g_failures == 0 ? 0 : 1;
}
