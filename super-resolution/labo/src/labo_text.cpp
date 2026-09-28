#include "labo_text.h"

#include <algorithm>

#include "labo_font.h"

namespace labo {

uint32_t DecodeUtf8(std::string_view text, size_t* pos)
{
    const size_t i = *pos;
    const auto byte = [&](size_t k) {
        return static_cast<uint32_t>(static_cast<unsigned char>(text[k]));
    };
    const uint32_t b0 = byte(i);
    uint32_t cp = 0;
    size_t len = 0;
    if (b0 < 0x80) {
        cp = b0;
        len = 1;
    } else if ((b0 & 0xE0) == 0xC0) {
        cp = b0 & 0x1F;
        len = 2;
    } else if ((b0 & 0xF0) == 0xE0) {
        cp = b0 & 0x0F;
        len = 3;
    } else if ((b0 & 0xF8) == 0xF0) {
        cp = b0 & 0x07;
        len = 4;
    } else {
        *pos = i + 1;
        return 0xFFFD;
    }
    if (i + len > text.size()) {
        *pos = i + 1;
        return 0xFFFD;
    }
    for (size_t k = 1; k < len; ++k) {
        const uint32_t b = byte(i + k);
        if ((b & 0xC0) != 0x80) {
            *pos = i + 1;
            return 0xFFFD;
        }
        cp = (cp << 6) | (b & 0x3F);
    }
    *pos = i + len;
    return cp;
}

uint32_t Utf8Length(std::string_view text)
{
    uint32_t n = 0;
    for (size_t pos = 0; pos < text.size(); ++n)
        DecodeUtf8(text, &pos);
    return n;
}

uint32_t GlyphIndex(uint32_t codepoint)
{
    const uint32_t* begin = font::kCodepoints;
    const uint32_t* end = font::kCodepoints + font::kGlyphCount;
    const uint32_t* it = std::lower_bound(begin, end, codepoint);
    if (it != end && *it == codepoint)
        return static_cast<uint32_t>(it - begin);
    if (codepoint == '?')
        return 0;  // impossible : '?' est dans la police
    return GlyphIndex('?');
}

void TextGrid::Resize(uint32_t cols, uint32_t rows)
{
    cols_ = cols;
    rows_ = rows;
    cells_.assign(static_cast<size_t>(cols) * rows, 0u);
}

void TextGrid::Clear()
{
    std::fill(cells_.begin(), cells_.end(), 0u);
}

uint32_t TextGrid::At(uint32_t col, uint32_t row) const
{
    if (col >= cols_ || row >= rows_)
        return 0;
    return cells_[static_cast<size_t>(row) * cols_ + col];
}

int TextGrid::Print(int col, int row, std::string_view utf8, Color color,
                    uint32_t flags)
{
    size_t pos = 0;
    while (pos < utf8.size()) {
        const uint32_t cp = DecodeUtf8(utf8, &pos);
        if (row >= 0 && col >= 0 && static_cast<uint32_t>(row) < rows_ &&
            static_cast<uint32_t>(col) < cols_) {
            uint32_t& cell = cells_[static_cast<size_t>(row) * cols_ + col];
            const uint32_t glyph = cp == ' ' ? 0u : GlyphIndex(cp);
            cell = (cell & (kCellPanel | kCellHighlight)) | flags | glyph |
                   (static_cast<uint32_t>(color) << kCellColorShift);
        }
        ++col;
    }
    return col;
}

int TextGrid::PrintRight(int endCol, int row, std::string_view utf8,
                         Color color, uint32_t flags)
{
    return Print(endCol - static_cast<int>(Utf8Length(utf8)), row, utf8,
                 color, flags);
}

void TextGrid::AddFlags(int col, int row, int width, int height,
                        uint32_t flags)
{
    for (int y = std::max(row, 0);
         y < std::min(row + height, static_cast<int>(rows_)); ++y)
        for (int x = std::max(col, 0);
             x < std::min(col + width, static_cast<int>(cols_)); ++x)
            cells_[static_cast<size_t>(y) * cols_ + x] |= flags;
}

} // namespace labo
