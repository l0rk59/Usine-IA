#include "labo_png.h"

#include <cstdio>

namespace labo {

namespace {

uint32_t Crc32(const uint8_t* data, size_t n, uint32_t crc = 0)
{
    crc = ~crc;
    for (size_t i = 0; i < n; ++i) {
        crc ^= data[i];
        for (int k = 0; k < 8; ++k)
            crc = (crc >> 1) ^ (0xEDB88320u & (0u - (crc & 1u)));
    }
    return ~crc;
}

void Be32(std::vector<uint8_t>& out, uint32_t v)
{
    out.push_back(static_cast<uint8_t>(v >> 24));
    out.push_back(static_cast<uint8_t>(v >> 16));
    out.push_back(static_cast<uint8_t>(v >> 8));
    out.push_back(static_cast<uint8_t>(v));
}

void Chunk(std::vector<uint8_t>& out, const char* tag,
           const std::vector<uint8_t>& data)
{
    Be32(out, static_cast<uint32_t>(data.size()));
    std::vector<uint8_t> body(tag, tag + 4);
    body.insert(body.end(), data.begin(), data.end());
    out.insert(out.end(), body.begin(), body.end());
    Be32(out, Crc32(body.data(), body.size()));
}

} // namespace

bool WritePng(const std::string& path, const std::vector<uint8_t>& rgba,
              uint32_t width, uint32_t height)
{
    if (rgba.size() < static_cast<size_t>(width) * height * 4)
        return false;
    // Donnees brutes : filtre 0 puis RGB, ligne par ligne.
    std::vector<uint8_t> raw;
    raw.reserve(static_cast<size_t>(height) * (width * 3 + 1));
    for (uint32_t y = 0; y < height; ++y) {
        raw.push_back(0);
        for (uint32_t x = 0; x < width; ++x) {
            const uint8_t* p = &rgba[(static_cast<size_t>(y) * width + x) * 4];
            raw.insert(raw.end(), p, p + 3);
        }
    }
    // Flux zlib en blocs "stockes" (non compresses) de 65535 octets max.
    std::vector<uint8_t> z = {0x78, 0x01};
    uint32_t a = 1, b = 0;
    for (uint8_t v : raw) {
        a = (a + v) % 65521;
        b = (b + a) % 65521;
    }
    for (size_t off = 0; off < raw.size() || off == 0;) {
        const size_t len = raw.size() - off < 65535 ? raw.size() - off : 65535;
        const bool last = off + len >= raw.size();
        z.push_back(last ? 1 : 0);
        z.push_back(static_cast<uint8_t>(len));
        z.push_back(static_cast<uint8_t>(len >> 8));
        z.push_back(static_cast<uint8_t>(~len));
        z.push_back(static_cast<uint8_t>(~len >> 8));
        z.insert(z.end(), raw.begin() + off, raw.begin() + off + len);
        off += len;
        if (last)
            break;
    }
    Be32(z, (b << 16) | a);

    std::vector<uint8_t> png = {0x89, 'P', 'N', 'G', '\r', '\n', 0x1A, '\n'};
    std::vector<uint8_t> ihdr;
    Be32(ihdr, width);
    Be32(ihdr, height);
    ihdr.insert(ihdr.end(), {8, 2, 0, 0, 0});  // 8 bits, RGB
    Chunk(png, "IHDR", ihdr);
    Chunk(png, "IDAT", z);
    Chunk(png, "IEND", {});

    FILE* f = std::fopen(path.c_str(), "wb");
    if (!f)
        return false;
    const bool ok = std::fwrite(png.data(), 1, png.size(), f) == png.size();
    return std::fclose(f) == 0 && ok;
}

} // namespace labo
