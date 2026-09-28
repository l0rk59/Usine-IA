// USR Labo -- grille de texte affichee par-dessus l'image (menu, mesures).
//
// Independant de toute API graphique : la grille est un simple tableau de
// cellules 32 bits, envoye tel quel au shader labo_compose.hlsl.

#pragma once

#include <cstdint>
#include <string_view>
#include <vector>

namespace labo {

enum Color : uint32_t {
    kWhite = 0,
    kGray = 1,
    kYellow = 2,
    kCyan = 3,
    kGreen = 4,
    kRed = 5,
    kOrange = 6,
    kViolet = 7,
};

// Drapeaux d'une cellule (memes valeurs que LABO_CELL_* du shader).
constexpr uint32_t kCellGlyphMask = 0x00000FFFu;
constexpr uint32_t kCellColorShift = 12u;
constexpr uint32_t kCellPanel = 0x00010000u;
constexpr uint32_t kCellHighlight = 0x00020000u;

// Decode le point de code UTF-8 qui commence en text[*pos] et avance *pos.
// Sequence invalide : renvoie U+FFFD et avance d'un octet.
uint32_t DecodeUtf8(std::string_view text, size_t* pos);

// Nombre de points de code (= de cellules occupees) d'une chaine UTF-8.
uint32_t Utf8Length(std::string_view text);

// Numero de glyphe dans la police du Labo ; '?' si le caractere manque.
uint32_t GlyphIndex(uint32_t codepoint);

class TextGrid {
public:
    void Resize(uint32_t cols, uint32_t rows);
    void Clear();

    uint32_t cols() const { return cols_; }
    uint32_t rows() const { return rows_; }
    const std::vector<uint32_t>& cells() const { return cells_; }
    uint32_t At(uint32_t col, uint32_t row) const;

    // Ecrit une chaine UTF-8 a partir de (col, row), coupee au bord.
    // Renvoie la colonne qui suit le dernier caractere.
    int Print(int col, int row, std::string_view utf8, Color color,
              uint32_t flags = 0);
    // Ecrit en alignant la fin de la chaine sur la colonne endCol (exclue).
    int PrintRight(int endCol, int row, std::string_view utf8, Color color,
                   uint32_t flags = 0);
    // Ajoute des drapeaux (panneau, surbrillance) a un rectangle.
    void AddFlags(int col, int row, int width, int height, uint32_t flags);

private:
    uint32_t cols_ = 0;
    uint32_t rows_ = 0;
    std::vector<uint32_t> cells_;
};

} // namespace labo
