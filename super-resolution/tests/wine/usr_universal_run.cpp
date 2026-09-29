// Banc de test de bout en bout de USR Universel (bibliotheque C++ reelle,
// Direct3D 12 reel) : lit une sequence d'images, appelle DispatchUniversal
// image par image et ecrit les sorties. Sous Linux, s'execute avec Wine +
// vkd3d-proton (voir tests/wine/universel_wine.sh) ; sous Windows tel quel.
//
//   usr_universal_run.exe entree.bin sortie.bin [poids.bin]
//
// entree.bin : en-tete de 8 uint32 (magic 'USRU', rw, rh, dw, dh, images,
// periode, drapeaux), puis par image : jitter (2 float) et l'image RGBA8.
// sortie.bin : par image, l'image d'affichage en RGBA16F (dw*dh*8 octets),
// suivie, si le bit 2 est mis, de l'image generee entre la sortie
// precedente et celle-ci (InterpolateUniversal, t = 0,5) -- ou de la sortie
// elle-meme quand il n'y a pas encore de flot (NotReady).
// drapeaux : bit 0 = sans reseau, bit 1 = remise a zero a l'image 12,
// bit 2 = generation d'images, bits 8..15 = accentuation * 255.

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <initializer_list>
#include <vector>

#include <d3d12.h>
#include <dxgi1_4.h>

#include "usr/usr.h"

namespace {

struct Header {
    uint32_t magic, rw, rh, dw, dh, frames, period, flags;
};

bool Check(HRESULT hr, const char* what)
{
    if (FAILED(hr)) {
        std::fprintf(stderr, "echec : %s (0x%08lx)\n", what,
                     static_cast<unsigned long>(hr));
        return false;
    }
    return true;
}

D3D12_RESOURCE_BARRIER Barrier(ID3D12Resource* r, D3D12_RESOURCE_STATES a,
                               D3D12_RESOURCE_STATES b)
{
    D3D12_RESOURCE_BARRIER x = {};
    x.Type = D3D12_RESOURCE_BARRIER_TYPE_TRANSITION;
    x.Transition.pResource = r;
    x.Transition.Subresource = D3D12_RESOURCE_BARRIER_ALL_SUBRESOURCES;
    x.Transition.StateBefore = a;
    x.Transition.StateAfter = b;
    return x;
}

ID3D12Resource* Buffer(ID3D12Device* dev, D3D12_HEAP_TYPE type, UINT64 size,
                       D3D12_RESOURCE_STATES state)
{
    D3D12_HEAP_PROPERTIES hp = {};
    hp.Type = type;
    D3D12_RESOURCE_DESC d = {};
    d.Dimension = D3D12_RESOURCE_DIMENSION_BUFFER;
    d.Width = size;
    d.Height = 1;
    d.DepthOrArraySize = 1;
    d.MipLevels = 1;
    d.SampleDesc.Count = 1;
    d.Layout = D3D12_TEXTURE_LAYOUT_ROW_MAJOR;
    ID3D12Resource* r = nullptr;
    dev->CreateCommittedResource(&hp, D3D12_HEAP_FLAG_NONE, &d, state,
                                 nullptr, IID_PPV_ARGS(&r));
    return r;
}

ID3D12Resource* Texture(ID3D12Device* dev, uint32_t w, uint32_t h,
                        DXGI_FORMAT f, D3D12_RESOURCE_FLAGS flags,
                        D3D12_RESOURCE_STATES state)
{
    D3D12_HEAP_PROPERTIES hp = {};
    hp.Type = D3D12_HEAP_TYPE_DEFAULT;
    D3D12_RESOURCE_DESC d = {};
    d.Dimension = D3D12_RESOURCE_DIMENSION_TEXTURE2D;
    d.Width = w;
    d.Height = h;
    d.DepthOrArraySize = 1;
    d.MipLevels = 1;
    d.Format = f;
    d.SampleDesc.Count = 1;
    d.Flags = flags;
    ID3D12Resource* r = nullptr;
    dev->CreateCommittedResource(&hp, D3D12_HEAP_FLAG_NONE, &d, state,
                                 nullptr, IID_PPV_ARGS(&r));
    return r;
}

} // namespace

int main(int argc, char** argv)
{
    if (argc < 3) {
        std::fprintf(stderr, "usage : %s entree.bin sortie.bin [poids.bin]\n",
                     argv[0]);
        return 2;
    }
    FILE* in = std::fopen(argv[1], "rb");
    FILE* out = std::fopen(argv[2], "wb");
    if (!in || !out) {
        std::fprintf(stderr, "fichiers illisibles\n");
        return 2;
    }
    Header h = {};
    if (std::fread(&h, sizeof(h), 1, in) != 1 || h.magic != 0x55525355u) {
        std::fprintf(stderr, "en-tete invalide\n");
        return 2;
    }
    std::vector<float> weights;
    if (argc > 3) {
        FILE* wf = std::fopen(argv[3], "rb");
        if (!wf) return 2;
        weights.resize(484);
        const size_t n = std::fread(weights.data(), 4, 484, wf);
        std::fclose(wf);
        weights.resize(n);
    }

    ID3D12Device* dev = nullptr;
    if (!Check(D3D12CreateDevice(nullptr, D3D_FEATURE_LEVEL_11_0,
                                 IID_PPV_ARGS(&dev)), "D3D12CreateDevice"))
        return 1;
    D3D12_COMMAND_QUEUE_DESC qd = {};
    qd.Type = D3D12_COMMAND_LIST_TYPE_DIRECT;
    ID3D12CommandQueue* queue = nullptr;
    ID3D12CommandAllocator* alloc = nullptr;
    ID3D12GraphicsCommandList* cl = nullptr;
    ID3D12Fence* fence = nullptr;
    if (!Check(dev->CreateCommandQueue(&qd, IID_PPV_ARGS(&queue)), "file") ||
        !Check(dev->CreateCommandAllocator(D3D12_COMMAND_LIST_TYPE_DIRECT,
                                           IID_PPV_ARGS(&alloc)), "alloc") ||
        !Check(dev->CreateCommandList(0, D3D12_COMMAND_LIST_TYPE_DIRECT, alloc,
                                      nullptr, IID_PPV_ARGS(&cl)), "liste") ||
        !Check(dev->CreateFence(0, D3D12_FENCE_FLAG_NONE,
                                IID_PPV_ARGS(&fence)), "fence"))
        return 1;
    cl->Close();
    HANDLE event = CreateEventW(nullptr, FALSE, FALSE, nullptr);
    UINT64 fenceValue = 0;

    usr::UniversalCreateDesc cd = {};
    cd.device = dev;
    cd.renderWidth = h.rw;
    cd.renderHeight = h.rh;
    cd.displayWidth = h.dw;
    cd.displayHeight = h.dh;
    cd.maxFramesInFlight = 2;
    cd.jitterPeriod = h.period;
    cd.flags = (h.flags & 1u) ? usr::kCreateDisableNetwork : usr::kCreateNone;
    if (!weights.empty()) {
        cd.weights = weights.data();
        cd.weightCount = static_cast<uint32_t>(weights.size());
    }
    usr::UniversalContext* ctx = nullptr;
    const usr::Result cr = usr::CreateUniversalContext(cd, &ctx);
    if (cr != usr::Result::Ok) {
        std::fprintf(stderr, "CreateUniversalContext : %d\n",
                     static_cast<int>(cr));
        return 1;
    }

    // Image d'entree (RGBA8) + tampon d'envoi ; deux sorties (RGBA16F) en
    // alternance -- la precedente sert a la generation d'images --, l'image
    // generee, et leur relecture.
    const bool generation = (h.flags & 4u) != 0;
    ID3D12Resource* color = Texture(dev, h.rw, h.rh, DXGI_FORMAT_R8G8B8A8_UNORM,
                                    D3D12_RESOURCE_FLAG_NONE,
                                    D3D12_RESOURCE_STATE_COPY_DEST);
    ID3D12Resource* outputs[2];
    D3D12_RESOURCE_STATES outputState[2];
    for (int i = 0; i < 2; ++i) {
        outputs[i] = Texture(dev, h.dw, h.dh, DXGI_FORMAT_R16G16B16A16_FLOAT,
                             D3D12_RESOURCE_FLAG_ALLOW_UNORDERED_ACCESS,
                             D3D12_RESOURCE_STATE_UNORDERED_ACCESS);
        outputState[i] = D3D12_RESOURCE_STATE_UNORDERED_ACCESS;
    }
    ID3D12Resource* output = outputs[0];
    ID3D12Resource* mid = Texture(
        dev, h.dw, h.dh, DXGI_FORMAT_R16G16B16A16_FLOAT,
        D3D12_RESOURCE_FLAG_ALLOW_UNORDERED_ACCESS,
        D3D12_RESOURCE_STATE_UNORDERED_ACCESS);
    D3D12_PLACED_SUBRESOURCE_FOOTPRINT upFoot = {}, rbFoot = {};
    UINT64 upSize = 0, rbSize = 0;
    {
        D3D12_RESOURCE_DESC d = color->GetDesc();
        dev->GetCopyableFootprints(&d, 0, 1, 0, &upFoot, nullptr, nullptr,
                                   &upSize);
        d = output->GetDesc();
        dev->GetCopyableFootprints(&d, 0, 1, 0, &rbFoot, nullptr, nullptr,
                                   &rbSize);
    }
    ID3D12Resource* upload = Buffer(dev, D3D12_HEAP_TYPE_UPLOAD, upSize,
                                    D3D12_RESOURCE_STATE_GENERIC_READ);
    ID3D12Resource* readback = Buffer(dev, D3D12_HEAP_TYPE_READBACK, rbSize,
                                      D3D12_RESOURCE_STATE_COPY_DEST);
    ID3D12Resource* readbackMid = Buffer(dev, D3D12_HEAP_TYPE_READBACK, rbSize,
                                         D3D12_RESOURCE_STATE_COPY_DEST);
    if (!color || !outputs[0] || !outputs[1] || !mid || !upload ||
        !readback || !readbackMid) {
        std::fprintf(stderr, "ressources\n");
        return 1;
    }
    std::vector<uint8_t> image(static_cast<size_t>(h.rw) * h.rh * 4);
    std::vector<uint8_t> row(static_cast<size_t>(h.dw) * 8);

    for (uint32_t f = 0; f < h.frames; ++f) {
        float jitter[2];
        if (std::fread(jitter, 4, 2, in) != 2 ||
            std::fread(image.data(), 1, image.size(), in) != image.size()) {
            std::fprintf(stderr, "entree tronquee (image %u)\n", f);
            return 1;
        }
        const int oi = static_cast<int>(f & 1u);
        output = outputs[oi];
        ID3D12Resource* previous = outputs[oi ^ 1];
        uint8_t* dst = nullptr;
        upload->Map(0, nullptr, reinterpret_cast<void**>(&dst));
        for (uint32_t y = 0; y < h.rh; ++y)
            std::memcpy(dst + upFoot.Offset + y * upFoot.Footprint.RowPitch,
                        image.data() + static_cast<size_t>(y) * h.rw * 4,
                        static_cast<size_t>(h.rw) * 4);
        upload->Unmap(0, nullptr);

        alloc->Reset();
        cl->Reset(alloc, nullptr);
        D3D12_TEXTURE_COPY_LOCATION src = {}, dstl = {};
        src.pResource = upload;
        src.Type = D3D12_TEXTURE_COPY_TYPE_PLACED_FOOTPRINT;
        src.PlacedFootprint = upFoot;
        dstl.pResource = color;
        dstl.Type = D3D12_TEXTURE_COPY_TYPE_SUBRESOURCE_INDEX;
        cl->CopyTextureRegion(&dstl, 0, 0, 0, &src, nullptr);
        D3D12_RESOURCE_BARRIER b = Barrier(
            color, D3D12_RESOURCE_STATE_COPY_DEST,
            D3D12_RESOURCE_STATE_NON_PIXEL_SHADER_RESOURCE);
        cl->ResourceBarrier(1, &b);
        if (outputState[oi] != D3D12_RESOURCE_STATE_UNORDERED_ACCESS) {
            b = Barrier(output, outputState[oi],
                        D3D12_RESOURCE_STATE_UNORDERED_ACCESS);
            cl->ResourceBarrier(1, &b);
            outputState[oi] = D3D12_RESOURCE_STATE_UNORDERED_ACCESS;
        }

        usr::UniversalDispatchDesc d = {};
        d.commandList = cl;
        d.color = color;
        d.output = output;
        d.jitterX = jitter[0];
        d.jitterY = jitter[1];
        d.reset = (h.flags & 2u) && f == 12;
        d.sharpness = static_cast<float>((h.flags >> 8) & 255u) / 255.0f;
        const usr::Result r = usr::DispatchUniversal(ctx, d);
        if (r != usr::Result::Ok) {
            std::fprintf(stderr, "DispatchUniversal : %d\n",
                         static_cast<int>(r));
            return 1;
        }

        D3D12_RESOURCE_BARRIER bb[2] = {
            Barrier(color, D3D12_RESOURCE_STATE_NON_PIXEL_SHADER_RESOURCE,
                    D3D12_RESOURCE_STATE_COPY_DEST),
            Barrier(output, D3D12_RESOURCE_STATE_UNORDERED_ACCESS,
                    D3D12_RESOURCE_STATE_NON_PIXEL_SHADER_RESOURCE)};
        cl->ResourceBarrier(2, bb);
        outputState[oi] = D3D12_RESOURCE_STATE_NON_PIXEL_SHADER_RESOURCE;

        // Image generee entre la sortie precedente et celle-ci.
        ID3D12Resource* midSource = output;
        if (generation &&
            outputState[oi ^ 1] ==
                D3D12_RESOURCE_STATE_NON_PIXEL_SHADER_RESOURCE) {
            usr::UniversalInterpolateDesc id = {};
            id.commandList = cl;
            id.previous = previous;
            id.current = output;
            id.output = mid;
            const usr::Result ir = usr::InterpolateUniversal(ctx, id);
            if (ir == usr::Result::Ok) {
                midSource = mid;
            } else if (ir != usr::Result::NotReady) {
                std::fprintf(stderr, "InterpolateUniversal : %d\n",
                             static_cast<int>(ir));
                return 1;
            }
        }

        D3D12_TEXTURE_COPY_LOCATION rs = {}, rd = {};
        auto readBack = [&](ID3D12Resource* source, ID3D12Resource* target,
                            D3D12_RESOURCE_STATES state) {
            D3D12_RESOURCE_BARRIER x =
                Barrier(source, state, D3D12_RESOURCE_STATE_COPY_SOURCE);
            cl->ResourceBarrier(1, &x);
            rs.pResource = source;
            rs.Type = D3D12_TEXTURE_COPY_TYPE_SUBRESOURCE_INDEX;
            rd.pResource = target;
            rd.Type = D3D12_TEXTURE_COPY_TYPE_PLACED_FOOTPRINT;
            rd.PlacedFootprint = rbFoot;
            cl->CopyTextureRegion(&rd, 0, 0, 0, &rs, nullptr);
            x = Barrier(source, D3D12_RESOURCE_STATE_COPY_SOURCE, state);
            cl->ResourceBarrier(1, &x);
        };
        readBack(output, readback,
                 D3D12_RESOURCE_STATE_NON_PIXEL_SHADER_RESOURCE);
        if (generation)
            readBack(midSource, readbackMid,
                     midSource == mid
                         ? D3D12_RESOURCE_STATE_UNORDERED_ACCESS
                         : D3D12_RESOURCE_STATE_NON_PIXEL_SHADER_RESOURCE);
        cl->Close();
        ID3D12CommandList* lists[] = {cl};
        queue->ExecuteCommandLists(1, lists);
        queue->Signal(fence, ++fenceValue);
        fence->SetEventOnCompletion(fenceValue, event);
        WaitForSingleObject(event, INFINITE);

        for (ID3D12Resource* buffer : {readback, readbackMid}) {
            if (buffer == readbackMid && !generation)
                break;
            uint8_t* rb = nullptr;
            D3D12_RANGE range = {0, static_cast<SIZE_T>(rbSize)};
            buffer->Map(0, &range, reinterpret_cast<void**>(&rb));
            for (uint32_t y = 0; y < h.dh; ++y) {
                std::memcpy(row.data(),
                            rb + rbFoot.Offset + y * rbFoot.Footprint.RowPitch,
                            row.size());
                std::fwrite(row.data(), 1, row.size(), out);
            }
            D3D12_RANGE none = {0, 0};
            buffer->Unmap(0, &none);
        }
    }
    std::fclose(out);
    std::fclose(in);
    usr::DestroyUniversalContext(ctx);
    std::printf("USR Universel : %u images traitees\n", h.frames);
    return 0;
}
