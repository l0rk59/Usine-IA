#ifndef NOMINMAX
#define NOMINMAX  // windows.h (via d3d12.h) ne doit pas definir min / max
#endif
#include "labo_renderer.h"

#include <algorithm>
#include <cmath>
#include <cstring>

#include "labo_font.h"
#include "labo_models.h"
#include "labo_shaders.h"  // genere par CMake (dxc -Fh)

namespace labo {

namespace {

constexpr uint32_t kSrvCount = 6;             // t0..t5
constexpr uint32_t kUavCount = 3;             // u0..u2
constexpr uint32_t kDescPerPass = kSrvCount + kUavCount;
constexpr uint32_t kMaxPassesPerFrame = 8;
constexpr uint32_t kDescPerSlot = kDescPerPass * kMaxPassesPerFrame;
constexpr uint32_t kTimestamps = 7;           // T0..T6
constexpr uint32_t kSceneCbSize = 512;        // >= sizeof(SceneConstants)
constexpr uint32_t kMaxTextCells = 256 * 128;

// Parametres racine : suivent LABO_ROOT_SIGNATURE.
enum : UINT { kRootConstants = 0, kRootScene = 1, kRootSrv = 2, kRootUav = 3 };

// Constantes de chaque passe : suivent les cbuffers des shaders.
struct SceneConsts {
    uint32_t size[2];
    float jitter[2];
};
struct TruthConsts {
    uint32_t size[2];
    uint32_t samples;
};
struct UpscaleConsts {
    uint32_t src[2];
    uint32_t dst[2];
    uint32_t mode;
};
struct ComposeConsts {
    uint32_t outSize[2];
    uint32_t textGrid[2];
    uint32_t cellSize[2];
    uint32_t glyphSize[2];
    uint32_t motionSize[2];
    float zoomCenter[2];
    uint32_t splitX;
    uint32_t leftView;
    uint32_t rightView;
    float zoomFactor;
    float zoomRadius;
    float motionScale;
};
static_assert(sizeof(ComposeConsts) == 18 * 4, "cbuffer LaboComposePass");
static_assert(sizeof(SceneConstants) <= kSceneCbSize, "cbuffer LaboScene");

template <typename T>
void SafeRelease(T*& p)
{
    if (p) {
        p->Release();
        p = nullptr;
    }
}

struct Tex {
    ID3D12Resource* res = nullptr;
    D3D12_RESOURCE_STATES state = D3D12_RESOURCE_STATE_COMMON;
    DXGI_FORMAT format = DXGI_FORMAT_UNKNOWN;
    uint32_t w = 0, h = 0;
};

// Ressource a lier a un emplacement t# / u# d'une passe.
struct Slot {
    ID3D12Resource* res = nullptr;
    DXGI_FORMAT format = DXGI_FORMAT_UNKNOWN;
    uint32_t bufferElements = 0;  // > 0 : StructuredBuffer<uint>
    uint64_t firstElement = 0;    // decalage dans le tampon (en uint)
};

Slot SlotOf(const Tex& t)
{
    return Slot{t.res, t.format, 0, 0};
}

class Barriers {
public:
    void Transition(Tex& t, D3D12_RESOURCE_STATES to)
    {
        if (!t.res || t.state == to)
            return;
        D3D12_RESOURCE_BARRIER b = {};
        b.Type = D3D12_RESOURCE_BARRIER_TYPE_TRANSITION;
        b.Transition.pResource = t.res;
        b.Transition.Subresource = D3D12_RESOURCE_BARRIER_ALL_SUBRESOURCES;
        b.Transition.StateBefore = t.state;
        b.Transition.StateAfter = to;
        list_.push_back(b);
        t.state = to;
    }
    void Flush(ID3D12GraphicsCommandList* cl)
    {
        if (!list_.empty())
            cl->ResourceBarrier(static_cast<UINT>(list_.size()), list_.data());
        list_.clear();
    }

private:
    std::vector<D3D12_RESOURCE_BARRIER> list_;
};

const D3D12_RESOURCE_STATES kRead =
    D3D12_RESOURCE_STATE_NON_PIXEL_SHADER_RESOURCE;
const D3D12_RESOURCE_STATES kWrite = D3D12_RESOURCE_STATE_UNORDERED_ACCESS;

} // namespace

struct Renderer::Impl {
    RendererDesc desc;
    ID3D12Device* device = nullptr;

    ID3D12RootSignature* rootSig = nullptr;
    ID3D12PipelineState* psoScene = nullptr;
    ID3D12PipelineState* psoTruth = nullptr;
    ID3D12PipelineState* psoUpscale = nullptr;
    ID3D12PipelineState* psoCompose = nullptr;
    ID3D12DescriptorHeap* heap = nullptr;
    UINT descSize = 0;

    // Tampons d'upload (lus directement par le GPU) : police, puis par
    // tranche : constantes de scene et grille de texte.
    ID3D12Resource* fontBuffer = nullptr;
    ID3D12Resource* upload = nullptr;
    uint8_t* uploadCpu = nullptr;
    UINT64 uploadSlotSize = 0;

    ID3D12QueryHeap* queries = nullptr;
    ID3D12Resource* queryReadback = nullptr;
    uint64_t* queryCpu = nullptr;
    std::vector<bool> slotUsed;
    double timestampFrequency = 1.0;

    // Resolution d'affichage
    Tex usrIA, usrSansIA, usrDebug, truth, bilinear, raw, composed;
    // Resolution de rendu
    uint32_t renderW = 0, renderH = 0;
    Tex color, depth, motion, plainColor, plainDepth, plainMotion;

    usr::Context* ctxIA = nullptr;
    usr::Context* ctxSansIA = nullptr;
    uint32_t model = ~0u;
    bool ctxIAFresh = true;
    bool ctxSansIAFresh = true;

    uint32_t frame = 0;
    uint32_t passIndex = 0;
    uint32_t slot = 0;
    Stats stats;
    TextGrid grid;
    float lastJitter[2] = {0, 0};

    // Capture
    struct Readback {
        ID3D12Resource* buf = nullptr;
        D3D12_PLACED_SUBRESOURCE_FOOTPRINT fp = {};
        uint32_t bytesPerPixel = 0;
    };
    Readback rbComposed, rbUsr, rbColor, rbDepth, rbMotion;
    float captureJitter[2] = {0, 0};

    // -------------------------------------------------------------------
    bool CreatePso(const void* code, size_t size, ID3D12PipelineState** out)
    {
        D3D12_COMPUTE_PIPELINE_STATE_DESC pd = {};
        pd.pRootSignature = rootSig;
        pd.CS.pShaderBytecode = code;
        pd.CS.BytecodeLength = size;
        return SUCCEEDED(device->CreateComputePipelineState(
            &pd, IID_PPV_ARGS(out)));
    }

    bool CreateTex(uint32_t w, uint32_t h, DXGI_FORMAT f, Tex* t)
    {
        SafeRelease(t->res);
        D3D12_HEAP_PROPERTIES hp = {};
        hp.Type = D3D12_HEAP_TYPE_DEFAULT;
        D3D12_RESOURCE_DESC rd = {};
        rd.Dimension = D3D12_RESOURCE_DIMENSION_TEXTURE2D;
        rd.Width = w;
        rd.Height = h;
        rd.DepthOrArraySize = 1;
        rd.MipLevels = 1;
        rd.Format = f;
        rd.SampleDesc.Count = 1;
        rd.Flags = D3D12_RESOURCE_FLAG_ALLOW_UNORDERED_ACCESS;
        t->state = kWrite;
        t->format = f;
        t->w = w;
        t->h = h;
        return SUCCEEDED(device->CreateCommittedResource(
            &hp, D3D12_HEAP_FLAG_NONE, &rd, t->state, nullptr,
            IID_PPV_ARGS(&t->res)));
    }

    ID3D12Resource* CreateBuffer(UINT64 size, D3D12_HEAP_TYPE type,
                                 D3D12_RESOURCE_STATES state)
    {
        D3D12_HEAP_PROPERTIES hp = {};
        hp.Type = type;
        D3D12_RESOURCE_DESC bd = {};
        bd.Dimension = D3D12_RESOURCE_DIMENSION_BUFFER;
        bd.Width = size;
        bd.Height = 1;
        bd.DepthOrArraySize = 1;
        bd.MipLevels = 1;
        bd.SampleDesc.Count = 1;
        bd.Layout = D3D12_TEXTURE_LAYOUT_ROW_MAJOR;
        ID3D12Resource* r = nullptr;
        if (FAILED(device->CreateCommittedResource(&hp, D3D12_HEAP_FLAG_NONE,
                                                   &bd, state, nullptr,
                                                   IID_PPV_ARGS(&r))))
            return nullptr;
        return r;
    }

    void ReleaseRenderSize()
    {
        usr::DestroyContext(ctxIA);
        usr::DestroyContext(ctxSansIA);
        ctxIA = ctxSansIA = nullptr;
        for (Tex* t : {&color, &depth, &motion, &plainColor, &plainDepth,
                       &plainMotion})
            SafeRelease(t->res);
        renderW = renderH = 0;
    }

    bool CreateContexts(uint32_t rw, uint32_t rh, uint32_t wantModel)
    {
        usr::CreateDesc cd = {};
        cd.device = device;
        cd.renderWidth = rw;
        cd.renderHeight = rh;
        cd.displayWidth = desc.displayWidth;
        cd.displayHeight = desc.displayHeight;
        cd.maxFramesInFlight = desc.framesInFlight;
        cd.weights = models::kModels[wantModel];
        cd.weightCount = models::kWeightCount;
        if (usr::CreateContext(cd, &ctxIA) != usr::Result::Ok)
            return false;
        cd.flags = usr::kCreateDisableNetwork;
        cd.weights = nullptr;
        cd.weightCount = 0;
        if (usr::CreateContext(cd, &ctxSansIA) != usr::Result::Ok)
            return false;
        model = wantModel;
        ctxIAFresh = ctxSansIAFresh = true;
        return true;
    }

    bool EnsureRenderSize(uint32_t rw, uint32_t rh, uint32_t wantModel)
    {
        if (rw == renderW && rh == renderH && ctxIA) {
            if (wantModel != model) {
                if (desc.waitForGpu)
                    desc.waitForGpu();
                usr::SetWeights(ctxIA, models::kModels[wantModel],
                                models::kWeightCount);
                model = wantModel;
            }
            return true;
        }
        if (desc.waitForGpu)
            desc.waitForGpu();
        ReleaseRenderSize();
        const bool ok =
            CreateTex(rw, rh, DXGI_FORMAT_R16G16B16A16_FLOAT, &color) &&
            CreateTex(rw, rh, DXGI_FORMAT_R32_FLOAT, &depth) &&
            CreateTex(rw, rh, DXGI_FORMAT_R16G16_FLOAT, &motion) &&
            CreateTex(rw, rh, DXGI_FORMAT_R16G16B16A16_FLOAT, &plainColor) &&
            CreateTex(rw, rh, DXGI_FORMAT_R32_FLOAT, &plainDepth) &&
            CreateTex(rw, rh, DXGI_FORMAT_R16G16_FLOAT, &plainMotion) &&
            CreateContexts(rw, rh, wantModel);
        if (!ok)
            return false;
        renderW = rw;
        renderH = rh;
        return true;
    }

    D3D12_CPU_DESCRIPTOR_HANDLE Cpu(uint32_t i) const
    {
        D3D12_CPU_DESCRIPTOR_HANDLE h = heap->GetCPUDescriptorHandleForHeapStart();
        h.ptr += static_cast<SIZE_T>(i) * descSize;
        return h;
    }

    D3D12_GPU_DESCRIPTOR_HANDLE Gpu(uint32_t i) const
    {
        D3D12_GPU_DESCRIPTOR_HANDLE h = heap->GetGPUDescriptorHandleForHeapStart();
        h.ptr += static_cast<UINT64>(i) * descSize;
        return h;
    }

    void WriteSrv(uint32_t index, const Slot& s)
    {
        D3D12_SHADER_RESOURCE_VIEW_DESC d = {};
        d.Shader4ComponentMapping = D3D12_DEFAULT_SHADER_4_COMPONENT_MAPPING;
        if (s.bufferElements > 0) {
            d.Format = DXGI_FORMAT_UNKNOWN;
            d.ViewDimension = D3D12_SRV_DIMENSION_BUFFER;
            d.Buffer.FirstElement = s.firstElement;
            d.Buffer.NumElements = s.bufferElements;
            d.Buffer.StructureByteStride = 4;
        } else {
            d.Format = s.res ? s.format : DXGI_FORMAT_R32_FLOAT;
            d.ViewDimension = D3D12_SRV_DIMENSION_TEXTURE2D;
            d.Texture2D.MipLevels = 1;
        }
        device->CreateShaderResourceView(s.res, &d, Cpu(index));
    }

    void WriteUav(uint32_t index, const Slot& s)
    {
        D3D12_UNORDERED_ACCESS_VIEW_DESC d = {};
        d.Format = s.res ? s.format : DXGI_FORMAT_R32_FLOAT;
        d.ViewDimension = D3D12_UAV_DIMENSION_TEXTURE2D;
        device->CreateUnorderedAccessView(s.res, nullptr, &d, Cpu(index));
    }

    D3D12_GPU_VIRTUAL_ADDRESS SceneCb() const
    {
        return upload->GetGPUVirtualAddress() + uploadSlotSize * slot;
    }

    void BindLabo(ID3D12GraphicsCommandList* cl)
    {
        ID3D12DescriptorHeap* heaps[] = {heap};
        cl->SetDescriptorHeaps(1, heaps);
        cl->SetComputeRootSignature(rootSig);
        cl->SetComputeRootConstantBufferView(kRootScene, SceneCb());
    }

    void Pass(ID3D12GraphicsCommandList* cl, ID3D12PipelineState* pso,
              const void* consts, uint32_t constCount,
              std::initializer_list<Slot> srvs,
              std::initializer_list<Slot> uavs, uint32_t w, uint32_t h)
    {
        const uint32_t base = slot * kDescPerSlot +
                              (passIndex++ % kMaxPassesPerFrame) * kDescPerPass;
        uint32_t i = 0;
        for (const Slot& s : srvs)
            WriteSrv(base + i++, s);
        for (; i < kSrvCount; ++i)
            WriteSrv(base + i, Slot{});
        i = 0;
        for (const Slot& s : uavs)
            WriteUav(base + kSrvCount + i++, s);
        for (; i < kUavCount; ++i)
            WriteUav(base + kSrvCount + i, Slot{});
        cl->SetPipelineState(pso);
        cl->SetComputeRoot32BitConstants(kRootConstants, constCount, consts, 0);
        cl->SetComputeRootDescriptorTable(kRootSrv, Gpu(base));
        cl->SetComputeRootDescriptorTable(kRootUav, Gpu(base + kSrvCount));
        cl->Dispatch((w + 7) / 8, (h + 7) / 8, 1);
    }

    void Stamp(ID3D12GraphicsCommandList* cl, uint32_t k)
    {
        cl->EndQuery(queries, D3D12_QUERY_TYPE_TIMESTAMP,
                     slot * kTimestamps + k);
    }

    void ReadTimings(double dt)
    {
        if (dt > 0.0) {
            const double fps = 1.0 / dt;
            stats.fps = stats.fps == 0.0 ? fps : stats.fps * 0.9 + fps * 0.1;
        }
        if (!slotUsed[slot])
            return;
        const uint64_t* t = queryCpu + slot * kTimestamps;
        auto ms = [&](uint32_t a, uint32_t b) {
            return t[b] >= t[a]
                       ? static_cast<double>(t[b] - t[a]) * 1000.0 /
                             timestampFrequency
                       : 0.0;
        };
        const double sample[kPassCount] = {
            ms(0, 1),  // scene
            ms(3, 4),  // USR + IA
            ms(4, 5),  // USR sans IA
            ms(2, 3),  // verite
            ms(1, 2),  // comparaisons
            ms(5, 6),  // composition
        };
        for (uint32_t p = 0; p < kPassCount; ++p)
            stats.gpuMs[p] = stats.gpuMs[p] * 0.9 + sample[p] * 0.1;
        stats.gpuTotalMs = stats.gpuTotalMs * 0.9 + ms(0, 6) * 0.1;
    }

    Tex* ColorTexFor(View v)
    {
        switch (v) {
        case View::UsrIA: return &usrIA;
        case View::UsrSansIA: return &usrSansIA;
        case View::Bilineaire: return &bilinear;
        case View::Verite: return &truth;
        case View::EntreeBrute: return &raw;
        default: return &usrIA;  // vues de diagnostic : texture ignoree
        }
    }

    void UsrDispatch(ID3D12GraphicsCommandList* cl, usr::Context* ctx,
                     Tex& out, Tex* debug, const Settings& s, bool reset,
                     float strength)
    {
        Barriers b;
        b.Transition(color, kRead);
        b.Transition(depth, kRead);
        b.Transition(motion, kRead);
        b.Transition(out, kWrite);
        if (debug)
            b.Transition(*debug, kWrite);
        b.Flush(cl);
        usr::DispatchDesc d = {};
        d.commandList = cl;
        d.color = color.res;
        d.depth = depth.res;
        d.motionVectors = motion.res;
        d.output = out.res;
        d.jitterX = lastJitter[0];
        d.jitterY = lastJitter[1];
        d.motionScaleX = 1.0f / static_cast<float>(renderW);
        d.motionScaleY = 1.0f / static_cast<float>(renderH);
        usr::GetDepthParams(1.0f, 0.0f, true, true, &d.depthP0, &d.depthP1);
        d.sharpness = s.sharpness;
        d.reset = reset;
        d.networkStrength = strength;
        d.historyLength = s.historyLength;
        d.antiGhosting = s.antiGhosting;
        d.kernelWidth = s.kernelWidth;
        d.debugOutput = debug ? debug->res : nullptr;
        usr::Dispatch(ctx, d);
    }

    bool CreateReadback(const Tex& t, uint32_t bpp, Readback* rb)
    {
        SafeRelease(rb->buf);
        const D3D12_RESOURCE_DESC rd = t.res->GetDesc();
        UINT64 total = 0;
        device->GetCopyableFootprints(&rd, 0, 1, 0, &rb->fp, nullptr, nullptr,
                                      &total);
        rb->bytesPerPixel = bpp;
        rb->buf = CreateBuffer(total, D3D12_HEAP_TYPE_READBACK,
                               D3D12_RESOURCE_STATE_COPY_DEST);
        return rb->buf != nullptr;
    }

    void CopyOut(ID3D12GraphicsCommandList* cl, Tex& t, Readback& rb)
    {
        const D3D12_RESOURCE_STATES before = t.state;
        Barriers b;
        b.Transition(t, D3D12_RESOURCE_STATE_COPY_SOURCE);
        b.Flush(cl);
        D3D12_TEXTURE_COPY_LOCATION dst = {};
        dst.pResource = rb.buf;
        dst.Type = D3D12_TEXTURE_COPY_TYPE_PLACED_FOOTPRINT;
        dst.PlacedFootprint = rb.fp;
        D3D12_TEXTURE_COPY_LOCATION src = {};
        src.pResource = t.res;
        src.Type = D3D12_TEXTURE_COPY_TYPE_SUBRESOURCE_INDEX;
        src.SubresourceIndex = 0;
        cl->CopyTextureRegion(&dst, 0, 0, 0, &src, nullptr);
        b.Transition(t, before);
        b.Flush(cl);
    }

    template <typename T>
    bool ReadBack(Readback& rb, uint32_t w, uint32_t h, std::vector<T>* out)
    {
        void* p = nullptr;
        D3D12_RANGE all = {0, static_cast<SIZE_T>(rb.fp.Footprint.RowPitch) *
                                  rb.fp.Footprint.Height};
        if (FAILED(rb.buf->Map(0, &all, &p)))
            return false;
        const size_t rowBytes = static_cast<size_t>(w) * rb.bytesPerPixel;
        out->resize(rowBytes * h / sizeof(T));
        for (uint32_t y = 0; y < h; ++y)
            std::memcpy(reinterpret_cast<uint8_t*>(out->data()) + y * rowBytes,
                        static_cast<uint8_t*>(p) + rb.fp.Offset +
                            static_cast<size_t>(y) * rb.fp.Footprint.RowPitch,
                        rowBytes);
        D3D12_RANGE none = {0, 0};
        rb.buf->Unmap(0, &none);
        return true;
    }
};

// --------------------------------------------------------------------------

Renderer::Renderer() : impl_(new Impl) {}

Renderer::~Renderer()
{
    Shutdown();
    delete impl_;
}

bool Renderer::Init(const RendererDesc& desc, std::string* error)
{
    Impl& m = *impl_;
    auto fail = [error](const char* what) {
        if (error)
            *error = what;
        return false;
    };
    m.desc = desc;
    m.device = desc.device;
    if (!m.device || desc.displayWidth == 0 || desc.displayHeight == 0 ||
        desc.framesInFlight == 0)
        return fail("parametres invalides");
    m.device->AddRef();
    m.stats.device = desc.deviceName;
    m.stats.displayW = desc.displayWidth;
    m.stats.displayH = desc.displayHeight;

    if (FAILED(m.device->CreateRootSignature(
            0, g_labo_scene, sizeof(g_labo_scene), IID_PPV_ARGS(&m.rootSig))))
        return fail("signature racine du Labo");
    if (!m.CreatePso(g_labo_scene, sizeof(g_labo_scene), &m.psoScene) ||
        !m.CreatePso(g_labo_truth, sizeof(g_labo_truth), &m.psoTruth) ||
        !m.CreatePso(g_labo_upscale, sizeof(g_labo_upscale), &m.psoUpscale) ||
        !m.CreatePso(g_labo_compose, sizeof(g_labo_compose), &m.psoCompose))
        return fail("creation des pipelines du Labo");

    D3D12_DESCRIPTOR_HEAP_DESC hd = {};
    hd.Type = D3D12_DESCRIPTOR_HEAP_TYPE_CBV_SRV_UAV;
    hd.NumDescriptors = kDescPerSlot * desc.framesInFlight;
    hd.Flags = D3D12_DESCRIPTOR_HEAP_FLAG_SHADER_VISIBLE;
    if (FAILED(m.device->CreateDescriptorHeap(&hd, IID_PPV_ARGS(&m.heap))))
        return fail("tas de descripteurs");
    m.descSize = m.device->GetDescriptorHandleIncrementSize(hd.Type);

    // Police : en memoire d'upload, lue telle quelle par le GPU.
    const UINT64 fontBytes = sizeof(font::kData);
    m.fontBuffer = m.CreateBuffer(fontBytes, D3D12_HEAP_TYPE_UPLOAD,
                                  D3D12_RESOURCE_STATE_GENERIC_READ);
    if (!m.fontBuffer)
        return fail("tampon de police");
    void* p = nullptr;
    D3D12_RANGE none = {0, 0};
    if (FAILED(m.fontBuffer->Map(0, &none, &p)))
        return fail("tampon de police (map)");
    std::memcpy(p, font::kData, fontBytes);
    m.fontBuffer->Unmap(0, nullptr);

    // Par tranche : constantes de scene (512 o) + grille de texte.
    m.uploadSlotSize = kSceneCbSize + kMaxTextCells * 4;
    m.upload = m.CreateBuffer(m.uploadSlotSize * desc.framesInFlight,
                              D3D12_HEAP_TYPE_UPLOAD,
                              D3D12_RESOURCE_STATE_GENERIC_READ);
    if (!m.upload || FAILED(m.upload->Map(0, &none, reinterpret_cast<void**>(
                                                        &m.uploadCpu))))
        return fail("tampon d'upload");

    // Chronometres GPU
    D3D12_QUERY_HEAP_DESC qd = {};
    qd.Type = D3D12_QUERY_HEAP_TYPE_TIMESTAMP;
    qd.Count = kTimestamps * desc.framesInFlight;
    if (FAILED(m.device->CreateQueryHeap(&qd, IID_PPV_ARGS(&m.queries))))
        return fail("chronometres GPU");
    m.queryReadback = m.CreateBuffer(qd.Count * sizeof(uint64_t),
                                     D3D12_HEAP_TYPE_READBACK,
                                     D3D12_RESOURCE_STATE_COPY_DEST);
    D3D12_RANGE all = {0, qd.Count * sizeof(uint64_t)};
    if (!m.queryReadback ||
        FAILED(m.queryReadback->Map(0, &all,
                                    reinterpret_cast<void**>(&m.queryCpu))))
        return fail("lecture des chronometres");
    m.slotUsed.assign(desc.framesInFlight, false);
    UINT64 freq = 0;
    if (desc.queue && SUCCEEDED(desc.queue->GetTimestampFrequency(&freq)) &&
        freq > 0)
        m.timestampFrequency = static_cast<double>(freq);

    const uint32_t dw = desc.displayWidth, dh = desc.displayHeight;
    const bool ok =
        m.CreateTex(dw, dh, DXGI_FORMAT_R16G16B16A16_FLOAT, &m.usrIA) &&
        m.CreateTex(dw, dh, DXGI_FORMAT_R16G16B16A16_FLOAT, &m.usrSansIA) &&
        m.CreateTex(dw, dh, DXGI_FORMAT_R8G8B8A8_UNORM, &m.usrDebug) &&
        m.CreateTex(dw, dh, DXGI_FORMAT_R16G16B16A16_FLOAT, &m.truth) &&
        m.CreateTex(dw, dh, DXGI_FORMAT_R16G16B16A16_FLOAT, &m.bilinear) &&
        m.CreateTex(dw, dh, DXGI_FORMAT_R16G16B16A16_FLOAT, &m.raw) &&
        m.CreateTex(dw, dh, DXGI_FORMAT_R8G8B8A8_UNORM, &m.composed);
    if (!ok)
        return fail("textures d'affichage");

    // Grille de texte : cellules de 12x24, agrandies en 4K.
    const uint32_t scale = std::max(1u, static_cast<uint32_t>(
                                            std::lround(dh / 1080.0)));
    const uint32_t cols = std::min(dw / (font::kGlyphWidth * scale), 256u);
    const uint32_t rows = std::min(dh / (font::kGlyphHeight * scale), 128u);
    m.grid.Resize(cols, rows);
    return true;
}

void Renderer::Shutdown()
{
    Impl& m = *impl_;
    if (!m.device)
        return;
    m.ReleaseRenderSize();
    for (Impl::Readback* rb : {&m.rbComposed, &m.rbUsr, &m.rbColor, &m.rbDepth,
                               &m.rbMotion})
        SafeRelease(rb->buf);
    for (Tex* t : {&m.usrIA, &m.usrSansIA, &m.usrDebug, &m.truth, &m.bilinear,
                   &m.raw, &m.composed})
        SafeRelease(t->res);
    if (m.queryReadback && m.queryCpu)
        m.queryReadback->Unmap(0, nullptr);
    SafeRelease(m.queryReadback);
    SafeRelease(m.queries);
    if (m.upload && m.uploadCpu)
        m.upload->Unmap(0, nullptr);
    SafeRelease(m.upload);
    SafeRelease(m.fontBuffer);
    SafeRelease(m.heap);
    SafeRelease(m.psoCompose);
    SafeRelease(m.psoUpscale);
    SafeRelease(m.psoTruth);
    SafeRelease(m.psoScene);
    SafeRelease(m.rootSig);
    SafeRelease(m.device);
}

ID3D12Resource* Renderer::Output() const { return impl_->composed.res; }
const Stats& Renderer::stats() const { return impl_->stats; }

bool Renderer::Record(ID3D12GraphicsCommandList* cl, Controller& ctrl,
                      uint32_t slot, double dt)
{
    Impl& m = *impl_;
    const Settings& s = ctrl.settings();
    m.slot = slot % m.desc.framesInFlight;
    m.passIndex = 0;
    m.ReadTimings(dt);

    const uint32_t dw = m.desc.displayWidth, dh = m.desc.displayHeight;
    uint32_t rw, rh;
    RenderSize(s, dw, dh, &rw, &rh);
    if (!m.EnsureRenderSize(rw, rh, std::min(s.model, 2u)))
        return false;
    const uint32_t phases = JitterPhases(s, rw, dw);
    JitterOffset(s, m.frame, phases, &m.lastJitter[0], &m.lastJitter[1]);
    m.stats.renderW = rw;
    m.stats.renderH = rh;
    m.stats.jitterPhases = phases;

    // Ce qu'il faut calculer pour les vues affichees
    auto shows = [&](View v) {
        return (s.split > 0.0f && s.left == v) || (s.split < 1.0f && s.right == v);
    };
    const bool needDebug = (s.split > 0.0f && NeedsDebug(s.left)) ||
                           (s.split < 1.0f && NeedsDebug(s.right));
    const bool needIA = shows(View::UsrIA) || needDebug;
    const bool needSansIA = shows(View::UsrSansIA);
    const bool needBil = shows(View::Bilineaire);
    const bool needRaw = shows(View::EntreeBrute);
    const bool needTruth = shows(View::Verite);
    const bool reset = ctrl.TakeHistoryReset();

    // Constantes de scene et texte de cette tranche
    uint8_t* up = m.uploadCpu + m.uploadSlotSize * m.slot;
    SceneConstants sc;
    FillSceneConstants(ctrl.sceneNow(), ctrl.scenePrev(), &sc);
    std::memcpy(up, &sc, sizeof(sc));
    ctrl.BuildOverlay(m.grid, m.stats);
    std::memcpy(up + kSceneCbSize, m.grid.cells().data(),
                m.grid.cells().size() * 4);

    m.BindLabo(cl);
    m.Stamp(cl, 0);

    // --- la scene, comme un jeu la rendrait --------------------------------
    {
        Barriers b;
        b.Transition(m.color, kWrite);
        b.Transition(m.depth, kWrite);
        b.Transition(m.motion, kWrite);
        b.Flush(cl);
        const SceneConsts c = {{rw, rh}, {m.lastJitter[0], m.lastJitter[1]}};
        m.Pass(cl, m.psoScene, &c, 4, {},
               {SlotOf(m.color), SlotOf(m.depth), SlotOf(m.motion)}, rw, rh);
    }
    m.Stamp(cl, 1);

    // --- vues de comparaison sans intelligence ------------------------------
    if (needBil) {
        Barriers b;
        b.Transition(m.plainColor, kWrite);
        b.Flush(cl);
        const SceneConsts c = {{rw, rh}, {0.0f, 0.0f}};
        m.Pass(cl, m.psoScene, &c, 4, {},
               {SlotOf(m.plainColor), SlotOf(m.plainDepth),
                SlotOf(m.plainMotion)}, rw, rh);
        b.Transition(m.plainColor, kRead);
        b.Transition(m.bilinear, kWrite);
        b.Flush(cl);
        const UpscaleConsts u = {{rw, rh}, {dw, dh}, 0};
        m.Pass(cl, m.psoUpscale, &u, 5, {SlotOf(m.plainColor)},
               {SlotOf(m.bilinear)}, dw, dh);
    }
    if (needRaw) {
        Barriers b;
        b.Transition(m.color, kRead);
        b.Transition(m.raw, kWrite);
        b.Flush(cl);
        const UpscaleConsts u = {{rw, rh}, {dw, dh}, 1};
        m.Pass(cl, m.psoUpscale, &u, 5, {SlotOf(m.color)}, {SlotOf(m.raw)},
               dw, dh);
    }
    m.Stamp(cl, 2);

    if (needTruth) {
        Barriers b;
        b.Transition(m.truth, kWrite);
        b.Flush(cl);
        const TruthConsts c = {{dw, dh}, std::max(1u, std::min(4u,
                                                               s.truthSamples))};
        m.Pass(cl, m.psoTruth, &c, 3, {}, {SlotOf(m.truth)}, dw, dh);
    }
    m.Stamp(cl, 3);

    // --- USR, avec puis sans le reseau --------------------------------------
    if (needIA) {
        m.UsrDispatch(cl, m.ctxIA, m.usrIA, needDebug ? &m.usrDebug : nullptr,
                      s, reset || m.ctxIAFresh,
                      s.network ? s.networkStrength : 0.0f);
        m.ctxIAFresh = false;
    } else {
        m.ctxIAFresh = true;  // historique perime : repartira de zero
    }
    m.Stamp(cl, 4);
    if (needSansIA) {
        m.UsrDispatch(cl, m.ctxSansIA, m.usrSansIA, nullptr, s,
                      reset || m.ctxSansIAFresh, 0.0f);
        m.ctxSansIAFresh = false;
    } else {
        m.ctxSansIAFresh = true;
    }
    m.Stamp(cl, 5);

    // --- composition ----------------------------------------------------------
    m.BindLabo(cl);  // USR a lie son propre tas et sa signature
    {
        Tex* left = m.ColorTexFor(s.left);
        Tex* right = m.ColorTexFor(s.right);
        Barriers b;
        for (Tex* t : {&m.usrIA, &m.usrSansIA, &m.usrDebug, &m.truth,
                       &m.bilinear, &m.raw, &m.motion})
            b.Transition(*t, kRead);
        b.Transition(m.composed, kWrite);
        b.Flush(cl);
        ComposeConsts c = {};
        c.outSize[0] = dw;
        c.outSize[1] = dh;
        c.textGrid[0] = m.grid.cols();
        c.textGrid[1] = m.grid.rows();
        const uint32_t scale = std::max(1u, static_cast<uint32_t>(
                                                std::lround(dh / 1080.0)));
        c.cellSize[0] = font::kGlyphWidth * scale;
        c.cellSize[1] = font::kGlyphHeight * scale;
        c.glyphSize[0] = font::kGlyphWidth;
        c.glyphSize[1] = font::kGlyphHeight;
        c.motionSize[0] = rw;
        c.motionSize[1] = rh;
        c.zoomCenter[0] = s.zoomX * static_cast<float>(dw);
        c.zoomCenter[1] = s.zoomY * static_cast<float>(dh);
        c.splitX = s.split >= 0.999f ? dw
                                     : static_cast<uint32_t>(s.split * dw);
        c.leftView = ComposeMode(s.left);
        c.rightView = ComposeMode(s.right);
        c.zoomFactor = static_cast<float>(s.zoom);
        c.zoomRadius = 0.18f * static_cast<float>(dh);
        c.motionScale = 4.0f;
        const Slot fontSlot = {m.fontBuffer, DXGI_FORMAT_UNKNOWN,
                               static_cast<uint32_t>(sizeof(font::kData) / 4),
                               0};
        // La grille de texte vit dans le tampon d'upload de la tranche,
        // juste apres les constantes de scene : vue "buffer" decalee.
        const Slot textSlot = {
            m.upload, DXGI_FORMAT_UNKNOWN, m.grid.cols() * m.grid.rows(),
            (m.uploadSlotSize * m.slot + kSceneCbSize) / 4};
        m.Pass(cl, m.psoCompose, &c, 18,
               {SlotOf(*left), SlotOf(*right), SlotOf(m.usrDebug),
                SlotOf(m.motion), fontSlot, textSlot},
               {SlotOf(m.composed)}, dw, dh);
    }
    m.Stamp(cl, 6);

    Barriers b;
    b.Transition(m.composed, D3D12_RESOURCE_STATE_COPY_SOURCE);
    b.Flush(cl);
    cl->ResolveQueryData(m.queries, D3D12_QUERY_TYPE_TIMESTAMP,
                         m.slot * kTimestamps, kTimestamps, m.queryReadback,
                         static_cast<UINT64>(m.slot) * kTimestamps *
                             sizeof(uint64_t));
    m.slotUsed[m.slot] = true;
    m.captureJitter[0] = m.lastJitter[0];
    m.captureJitter[1] = m.lastJitter[1];
    ++m.frame;
    return true;
}

void Renderer::RecordCapture(ID3D12GraphicsCommandList* cl)
{
    Impl& m = *impl_;
    if (!m.rbComposed.buf || m.rbColor.fp.Footprint.Width != m.renderW ||
        m.rbColor.fp.Footprint.Height != m.renderH) {
        m.CreateReadback(m.composed, 4, &m.rbComposed);
        m.CreateReadback(m.usrIA, 8, &m.rbUsr);
        m.CreateReadback(m.color, 8, &m.rbColor);
        m.CreateReadback(m.depth, 4, &m.rbDepth);
        m.CreateReadback(m.motion, 4, &m.rbMotion);
    }
    m.CopyOut(cl, m.composed, m.rbComposed);
    m.CopyOut(cl, m.usrIA, m.rbUsr);
    m.CopyOut(cl, m.color, m.rbColor);
    m.CopyOut(cl, m.depth, m.rbDepth);
    m.CopyOut(cl, m.motion, m.rbMotion);
}

bool Renderer::ReadCapture(Capture* out)
{
    Impl& m = *impl_;
    if (!m.rbComposed.buf)
        return false;
    out->displayW = m.desc.displayWidth;
    out->displayH = m.desc.displayHeight;
    out->renderW = m.renderW;
    out->renderH = m.renderH;
    out->jitter[0] = m.captureJitter[0];
    out->jitter[1] = m.captureJitter[1];
    return m.ReadBack(m.rbComposed, out->displayW, out->displayH,
                      &out->composed) &&
           m.ReadBack(m.rbUsr, out->displayW, out->displayH, &out->usrIA) &&
           m.ReadBack(m.rbColor, m.renderW, m.renderH, &out->sceneColor) &&
           m.ReadBack(m.rbDepth, m.renderW, m.renderH, &out->sceneDepth) &&
           m.ReadBack(m.rbMotion, m.renderW, m.renderH, &out->sceneMotion);
}

} // namespace labo
