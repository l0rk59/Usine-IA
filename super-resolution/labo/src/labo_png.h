// USR Labo -- ecriture PNG minimale (sans compression, sans dependance),
// pour les captures d'ecran du mode --capture.

#pragma once

#include <cstdint>
#include <string>
#include <vector>

namespace labo {

// Pixels RGBA8, ligne par ligne ; le canal alpha est ignore.
bool WritePng(const std::string& path, const std::vector<uint8_t>& rgba,
              uint32_t width, uint32_t height);

} // namespace labo
