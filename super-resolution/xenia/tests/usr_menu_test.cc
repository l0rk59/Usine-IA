// Tests du modele du menu USR de Xenia (src/xenia/app/usr_menu_model.h),
// sans Xenia ni ImGui :
//   g++ -std=c++20 -Wall -Wextra -Werror -I<xenia>/src usr_menu_test.cc
#include <cmath>
#include <cstdio>
#include <cstdlib>

#include "xenia/app/usr_menu_model.h"

using namespace xe::app::usr_menu;

static int failures = 0;
#define CHECK(cond)                                                   \
  do {                                                                \
    if (!(cond)) {                                                    \
      std::printf("ECHEC ligne %d : %s\n", __LINE__, #cond);          \
      ++failures;                                                     \
    }                                                                 \
  } while (0)

static void Select(Menu& m, Row r) { m.selected = int(r); }

int main() {
  Values v;
  Menu m;
  // navigation circulaire
  m.Move(-1);
  CHECK(m.SelectedRow() == Row::kReset);
  m.Move(1);
  CHECK(m.SelectedRow() == Row::kMethod);
  // methode : USR -> FSR -> CAS -> bilineaire -> USR
  CHECK(m.Adjust(v, 1) && v.method == Method::kFsr);
  CHECK(m.Adjust(v, 1) && v.method == Method::kCas);
  CHECK(m.Adjust(v, 1) && v.method == Method::kBilinear);
  CHECK(m.Adjust(v, 1) && v.method == Method::kUsr);
  CHECK(m.Adjust(v, -1) && v.method == Method::kBilinear);
  // reglages USR inactifs avec une autre methode
  Select(m, Row::kSharpness);
  CHECK(!RowEnabled(v, Row::kSharpness));
  CHECK(!m.Adjust(v, 1));
  v.method = Method::kUsr;
  // nettete bornee a [0, 1], pas de 0,05
  v.sharpness = 0.97f;
  CHECK(m.Adjust(v, 1) && v.sharpness == 1.0f);
  CHECK(!m.Adjust(v, 1));
  // historique : pas de 1 jusqu'a 16, puis 4, borne a [1, 64]
  Select(m, Row::kHistory);
  v.history_length = 15.0f;
  m.Adjust(v, 1);
  CHECK(v.history_length == 16.0f);
  m.Adjust(v, 1);
  CHECK(v.history_length == 20.0f);
  m.Adjust(v, -1);
  CHECK(v.history_length == 16.0f);
  m.Adjust(v, -1);
  CHECK(v.history_length == 15.0f);
  v.history_length = 64.0f;
  CHECK(!m.Adjust(v, 1));
  v.history_length = 1.0f;
  CHECK(!m.Adjust(v, -1));
  // anti-fantomes multiplicatif, arrondi au centieme, borne
  Select(m, Row::kAntiGhosting);
  v.anti_ghosting = 0.3f;
  m.Adjust(v, 1);
  CHECK(std::fabs(v.anti_ghosting - 0.38f) < 1e-6f);
  for (int i = 0; i < 40; ++i) m.Adjust(v, 1);
  CHECK(v.anti_ghosting == 4.0f);
  for (int i = 0; i < 60; ++i) m.Adjust(v, -1);
  CHECK(std::fabs(v.anti_ghosting - 0.05f) < 1e-6f);
  // force de l'IA inactive sans IA ; textures fines inactives au niveau 1
  Select(m, Row::kNetwork);
  bool changed = false;
  CHECK(!m.Activate(v, changed) && changed && !v.network);
  CHECK(!RowEnabled(v, Row::kStrength));
  Select(m, Row::kLevel);
  CHECK(!m.Activate(v, changed) && changed && !v.jitter);
  CHECK(!RowEnabled(v, Row::kLodBias));
  // sortie native (DLAA) et generation d'images : A bascule, inactives hors
  // USR, desactivees par defaut
  CHECK(!Values().native && !Values().frame_generation);
  Select(m, Row::kOutput);
  CHECK(!m.Activate(v, changed) && changed && v.native);
  CHECK(RowValue(v, Row::kOutput) == "native (DLAA) + FSR");
  Select(m, Row::kFrameGeneration);
  CHECK(!m.Activate(v, changed) && changed && v.frame_generation);
  CHECK(RowValue(v, Row::kFrameGeneration) == "x2 (jeux à 30 images/s)");
  v.method = Method::kFsr;
  CHECK(!RowEnabled(v, Row::kOutput) && !RowEnabled(v, Row::kFrameGeneration));
  CHECK(!m.Adjust(v, 1) && v.frame_generation);
  v.method = Method::kUsr;
  // « Oublier l'historique » : A demande la remise a zero
  Select(m, Row::kReset);
  CHECK(m.Activate(v, changed) && !changed);
  // textes
  CHECK(RowValue(v, Row::kLevel) == "1 (image telle quelle)");
  v.sharpness = 0.25f;
  CHECK(RowValue(v, Row::kSharpness) == "25 %");
  for (int i = 0; i < int(Row::kCount); ++i) {
    CHECK(RowLabel(Row(i))[0] != '?');
  }
  if (failures) {
    std::printf("%d echec(s)\n", failures);
    return 1;
  }
  std::printf("menu USR : tous les tests passent\n");
  return 0;
}
