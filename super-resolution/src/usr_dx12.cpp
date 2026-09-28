// USR -- implementation Direct3D 12 (PC et Xbox).
//
// Trois dispatchs compute par image, une signature racine commune (definie
// dans shaders/usr_common.hlsli et embarquee dans le bytecode), un tas de
// descripteurs propre au contexte, decoupe en tranches par image en vol.

#include "usr/usr.h"

#include <cmath>
#include <cstring>
#include <new>

#include "usr_default_weights.h"

#if !defined(USR_NO_BUILTIN_SHADERS)
#include "usr_shaders.h"  // genere par CMake (dxc -Fh)
#endif

namespace usr {

namespace {

constexpr float kSigmaSharpDisplay = 0.47f;  // = SIGMA_SHARP_DISPLAY
constexpr uint32_t kFlagReset = 1u;
constexpr uint32_t kFlagNetwork = 2u;
constexpr uint32_t kFlagDebug = 4u;
constexpr uint32_t kRootConstantCount = 20;

constexpr uint32_t kSrvCount = 4;  // t0..t3
constexpr uint32_t kUavCount = 3;  // u0..u2
constexpr uint32_t kPassCount = 3;
constexpr uint32_t kDescriptorsPerFrame = kPassCount * (kSrvCount + kUavCount);
constexpr uint32_t kWeightFloats = 484;             // 121 float4
constexpr uint32_t kWeightBufferSize = 2048;        // multiple de 256

// Parametres racine : doivent suivre USR_ROOT_SIGNATURE.
enum RootParam : UINT {
    kRootConstants = 0,
    kRootNetwork = 1,
    kRootSrvTable = 2,
    kRootUavTable = 3,
};

struct Constants {
    uint32_t renderSize[2];
    uint32_t displaySize[2];
    float jitter[2];
    float motionScale[2];
    float depthP0;
    float depthP1;
    float exposure;
    float sharpness;
    uint32_t flags;
    float sigmaSharp;
    float maxCount;
    float clipGamma;
    float netStrength;
    uint32_t reserved[3];
};
static_assert(sizeof(Constants) == kRootConstantCount * 4,
              "doit suivre le cbuffer USRConstants");

float Clamp(float v, float lo, float hi)
{
    return v < lo ? lo : (v > hi ? hi : v);
}

template <typename T>
void SafeRelease(T*& p)
{
    if (p) {
        p->Release();
        p = nullptr;
    }
}

struct Tracked {
    ID3D12Resource* resource = nullptr;
    D3D12_RESOURCE_STATES state = D3D12_RESOURCE_STATE_COMMON;
};

DXGI_FORMAT ReadableFormat(DXGI_FORMAT f)
{
    switch (f) {
    case DXGI_FORMAT_D32_FLOAT:
    case DXGI_FORMAT_R32_TYPELESS:
        return DXGI_FORMAT_R32_FLOAT;
    case DXGI_FORMAT_D24_UNORM_S8_UINT:
    case DXGI_FORMAT_R24G8_TYPELESS:
        return DXGI_FORMAT_R24_UNORM_X8_TYPELESS;
    case DXGI_FORMAT_D16_UNORM:
    case DXGI_FORMAT_R16_TYPELESS:
        return DXGI_FORMAT_R16_UNORM;
    case DXGI_FORMAT_D32_FLOAT_S8X24_UINT:
    case DXGI_FORMAT_R32G8X24_TYPELESS:
        return DXGI_FORMAT_R32_FLOAT_X8X24_TYPELESS;
    case DXGI_FORMAT_R16G16B16A16_TYPELESS:
        return DXGI_FORMAT_R16G16B16A16_FLOAT;
    case DXGI_FORMAT_R32G32B32A32_TYPELESS:
        return DXGI_FORMAT_R32G32B32A32_FLOAT;
    case DXGI_FORMAT_R16G16_TYPELESS:
        return DXGI_FORMAT_R16G16_FLOAT;
    case DXGI_FORMAT_R32G32_TYPELESS:
        return DXGI_FORMAT_R32G32_FLOAT;
    case DXGI_FORMAT_R8G8B8A8_TYPELESS:
        return DXGI_FORMAT_R8G8B8A8_UNORM;
    case DXGI_FORMAT_B8G8R8A8_TYPELESS:
        return DXGI_FORMAT_B8G8R8A8_UNORM;
    case DXGI_FORMAT_R10G10B10A2_TYPELESS:
        return DXGI_FORMAT_R10G10B10A2_UNORM;
    default:
        return f;
    }
}

// Formats sRGB : lisibles en SRV (decodes en lineaire), interdits en UAV.
bool IsSrgb(DXGI_FORMAT f)
{
    return f == DXGI_FORMAT_R8G8B8A8_UNORM_SRGB ||
           f == DXGI_FORMAT_B8G8R8A8_UNORM_SRGB ||
           f == DXGI_FORMAT_B8G8R8X8_UNORM_SRGB ||
           f == DXGI_FORMAT_BC1_UNORM_SRGB || f == DXGI_FORMAT_BC2_UNORM_SRGB ||
           f == DXGI_FORMAT_BC3_UNORM_SRGB || f == DXGI_FORMAT_BC7_UNORM_SRGB;
}

DXGI_FORMAT ViewFormat(ID3D12Resource* r, DXGI_FORMAT requested)
{
    if (requested != DXGI_FORMAT_UNKNOWN)
        return requested;
    return ReadableFormat(r->GetDesc().Format);
}

} // namespace

class Context {
public:
    Result Init(const CreateDesc& desc);
    void Release();
    Result Dispatch(const DispatchDesc& desc);
    Result SetWeights(const float* weights, uint32_t count);

private:
    Result CreateTexture(uint32_t w, uint32_t h, DXGI_FORMAT format,
                         Tracked* out);
    Result CreatePipeline(const ShaderBytecode& cs,
                          ID3D12PipelineState** out);
    void Transition(ID3D12GraphicsCommandList* cl, Tracked& t,
                    D3D12_RESOURCE_STATES to);
    D3D12_CPU_DESCRIPTOR_HANDLE Cpu(uint32_t index) const;
    D3D12_GPU_DESCRIPTOR_HANDLE Gpu(uint32_t index) const;
    void WriteSrv(uint32_t slot, ID3D12Resource* r, DXGI_FORMAT format);
    void WriteUav(uint32_t slot, ID3D12Resource* r, DXGI_FORMAT format);
    void WriteNullSrv(uint32_t slot);
    void WriteNullUav(uint32_t slot);

    CreateDesc desc_ = {};
    ID3D12Device* device_ = nullptr;
    ID3D12RootSignature* rootSignature_ = nullptr;
    ID3D12PipelineState* prepare_ = nullptr;
    ID3D12PipelineState* accumulate_ = nullptr;
    ID3D12PipelineState* sharpen_ = nullptr;
    ID3D12DescriptorHeap* heap_ = nullptr;
    UINT descriptorSize_ = 0;
    ID3D12Resource* weights_ = nullptr;
    void* weightsMapped_ = nullptr;

    Tracked dilatedMotion_;
    Tracked invZ_[2];
    Tracked disocclusion_;
    Tracked history_[2];

    uint64_t frame_ = 0;
    bool useNetwork_ = true;
};

// --------------------------------------------------------------------------

Result Context::Init(const CreateDesc& desc)
{
    desc_ = desc;
    device_ = desc.device;
    device_->AddRef();
    useNetwork_ = (desc.flags & kCreateDisableNetwork) == 0;
    if (desc_.maxFramesInFlight == 0)
        desc_.maxFramesInFlight = 1;

    ShaderBytecode prep = desc.prepareCS;
    ShaderBytecode accu = desc.accumulateCS;
    ShaderBytecode shrp = desc.sharpenCS;
#if !defined(USR_NO_BUILTIN_SHADERS)
    if (!prep.data) prep = {g_usr_prepare, sizeof(g_usr_prepare)};
    if (!accu.data) accu = {g_usr_accumulate, sizeof(g_usr_accumulate)};
    if (!shrp.data) shrp = {g_usr_sharpen, sizeof(g_usr_sharpen)};
#endif
    if (!prep.data || !accu.data || !shrp.data)
        return Result::InvalidArgument;

    // La signature racine est embarquee dans chaque shader ([RootSignature]).
    if (FAILED(device_->CreateRootSignature(0, prep.data, prep.size,
                                            IID_PPV_ARGS(&rootSignature_))))
        return Result::DeviceError;

    Result r;
    if ((r = CreatePipeline(prep, &prepare_)) != Result::Ok) return r;
    if ((r = CreatePipeline(accu, &accumulate_)) != Result::Ok) return r;
    if ((r = CreatePipeline(shrp, &sharpen_)) != Result::Ok) return r;

    D3D12_DESCRIPTOR_HEAP_DESC hd = {};
    hd.Type = D3D12_DESCRIPTOR_HEAP_TYPE_CBV_SRV_UAV;
    hd.NumDescriptors = kDescriptorsPerFrame * desc_.maxFramesInFlight;
    hd.Flags = D3D12_DESCRIPTOR_HEAP_FLAG_SHADER_VISIBLE;
    if (FAILED(device_->CreateDescriptorHeap(&hd, IID_PPV_ARGS(&heap_))))
        return Result::OutOfMemory;
    descriptorSize_ = device_->GetDescriptorHandleIncrementSize(hd.Type);

    const uint32_t rw = desc.renderWidth, rh = desc.renderHeight;
    const uint32_t dw = desc.displayWidth, dh = desc.displayHeight;
    if ((r = CreateTexture(rw, rh, DXGI_FORMAT_R16G16_FLOAT,
                           &dilatedMotion_)) != Result::Ok) return r;
    for (Tracked& t : invZ_)
        if ((r = CreateTexture(rw, rh, DXGI_FORMAT_R32_FLOAT, &t)) !=
            Result::Ok) return r;
    if ((r = CreateTexture(rw, rh, DXGI_FORMAT_R8_UNORM, &disocclusion_)) !=
        Result::Ok) return r;
    for (Tracked& t : history_)
        if ((r = CreateTexture(dw, dh, DXGI_FORMAT_R16G16B16A16_FLOAT, &t)) !=
            Result::Ok) return r;

    // Poids : petit tampon d'upload, mappe en permanence, lu en CBV racine.
    D3D12_HEAP_PROPERTIES hp = {};
    hp.Type = D3D12_HEAP_TYPE_UPLOAD;
    D3D12_RESOURCE_DESC bd = {};
    bd.Dimension = D3D12_RESOURCE_DIMENSION_BUFFER;
    bd.Width = kWeightBufferSize;
    bd.Height = 1;
    bd.DepthOrArraySize = 1;
    bd.MipLevels = 1;
    bd.SampleDesc.Count = 1;
    bd.Layout = D3D12_TEXTURE_LAYOUT_ROW_MAJOR;
    if (FAILED(device_->CreateCommittedResource(
            &hp, D3D12_HEAP_FLAG_NONE, &bd,
            D3D12_RESOURCE_STATE_GENERIC_READ, nullptr,
            IID_PPV_ARGS(&weights_))))
        return Result::OutOfMemory;
    D3D12_RANGE none = {0, 0};
    if (FAILED(weights_->Map(0, &none, &weightsMapped_)))
        return Result::DeviceError;
    std::memset(weightsMapped_, 0, kWeightBufferSize);

    if (desc.weights)
        return SetWeights(desc.weights, desc.weightCount);
    return SetWeights(detail::kDefaultWeights, detail::kDefaultWeightCount);
}

void Context::Release()
{
    if (weights_ && weightsMapped_)
        weights_->Unmap(0, nullptr);
    SafeRelease(weights_);
    for (Tracked& t : history_) SafeRelease(t.resource);
    SafeRelease(disocclusion_.resource);
    for (Tracked& t : invZ_) SafeRelease(t.resource);
    SafeRelease(dilatedMotion_.resource);
    SafeRelease(heap_);
    SafeRelease(sharpen_);
    SafeRelease(accumulate_);
    SafeRelease(prepare_);
    SafeRelease(rootSignature_);
    SafeRelease(device_);
}

Result Context::SetWeights(const float* weights, uint32_t count)
{
    // 482 poids utiles ; on accepte le format .bin complet (484, bourre).
    if (!weights || count < 482 || count > kWeightFloats)
        return Result::InvalidArgument;
    std::memset(weightsMapped_, 0, kWeightFloats * sizeof(float));
    std::memcpy(weightsMapped_, weights, count * sizeof(float));
    return Result::Ok;
}

Result Context::CreateTexture(uint32_t w, uint32_t h, DXGI_FORMAT format,
                              Tracked* out)
{
    D3D12_HEAP_PROPERTIES hp = {};
    hp.Type = D3D12_HEAP_TYPE_DEFAULT;
    D3D12_RESOURCE_DESC rd = {};
    rd.Dimension = D3D12_RESOURCE_DIMENSION_TEXTURE2D;
    rd.Width = w;
    rd.Height = h;
    rd.DepthOrArraySize = 1;
    rd.MipLevels = 1;
    rd.Format = format;
    rd.SampleDesc.Count = 1;
    rd.Layout = D3D12_TEXTURE_LAYOUT_UNKNOWN;
    rd.Flags = D3D12_RESOURCE_FLAG_ALLOW_UNORDERED_ACCESS;
    out->state = D3D12_RESOURCE_STATE_UNORDERED_ACCESS;
    if (FAILED(device_->CreateCommittedResource(
            &hp, D3D12_HEAP_FLAG_NONE, &rd, out->state, nullptr,
            IID_PPV_ARGS(&out->resource))))
        return Result::OutOfMemory;
    return Result::Ok;
}

Result Context::CreatePipeline(const ShaderBytecode& cs,
                               ID3D12PipelineState** out)
{
    D3D12_COMPUTE_PIPELINE_STATE_DESC pd = {};
    pd.pRootSignature = rootSignature_;
    pd.CS.pShaderBytecode = cs.data;
    pd.CS.BytecodeLength = cs.size;
    if (FAILED(device_->CreateComputePipelineState(&pd, IID_PPV_ARGS(out))))
        return Result::DeviceError;
    return Result::Ok;
}

void Context::Transition(ID3D12GraphicsCommandList* cl, Tracked& t,
                         D3D12_RESOURCE_STATES to)
{
    if (t.state == to)
        return;
    D3D12_RESOURCE_BARRIER b = {};
    b.Type = D3D12_RESOURCE_BARRIER_TYPE_TRANSITION;
    b.Transition.pResource = t.resource;
    b.Transition.Subresource = D3D12_RESOURCE_BARRIER_ALL_SUBRESOURCES;
    b.Transition.StateBefore = t.state;
    b.Transition.StateAfter = to;
    cl->ResourceBarrier(1, &b);
    t.state = to;
}

D3D12_CPU_DESCRIPTOR_HANDLE Context::Cpu(uint32_t index) const
{
    D3D12_CPU_DESCRIPTOR_HANDLE h = heap_->GetCPUDescriptorHandleForHeapStart();
    h.ptr += static_cast<SIZE_T>(index) * descriptorSize_;
    return h;
}

D3D12_GPU_DESCRIPTOR_HANDLE Context::Gpu(uint32_t index) const
{
    D3D12_GPU_DESCRIPTOR_HANDLE h = heap_->GetGPUDescriptorHandleForHeapStart();
    h.ptr += static_cast<UINT64>(index) * descriptorSize_;
    return h;
}

void Context::WriteSrv(uint32_t slot, ID3D12Resource* r, DXGI_FORMAT format)
{
    D3D12_SHADER_RESOURCE_VIEW_DESC d = {};
    d.Format = format;
    d.ViewDimension = D3D12_SRV_DIMENSION_TEXTURE2D;
    d.Shader4ComponentMapping = D3D12_DEFAULT_SHADER_4_COMPONENT_MAPPING;
    d.Texture2D.MipLevels = 1;
    device_->CreateShaderResourceView(r, &d, Cpu(slot));
}

void Context::WriteUav(uint32_t slot, ID3D12Resource* r, DXGI_FORMAT format)
{
    D3D12_UNORDERED_ACCESS_VIEW_DESC d = {};
    d.Format = format;
    d.ViewDimension = D3D12_UAV_DIMENSION_TEXTURE2D;
    device_->CreateUnorderedAccessView(r, nullptr, &d, Cpu(slot));
}

void Context::WriteNullSrv(uint32_t slot)
{
    WriteSrv(slot, nullptr, DXGI_FORMAT_R32_FLOAT);
}

void Context::WriteNullUav(uint32_t slot)
{
    WriteUav(slot, nullptr, DXGI_FORMAT_R32_FLOAT);
}

Result Context::Dispatch(const DispatchDesc& d)
{
    if (!d.commandList || !d.color || !d.depth || !d.motionVectors ||
        !d.output)
        return Result::InvalidArgument;

    const DXGI_FORMAT outputFormat = ViewFormat(d.output, d.outputFormat);
    if (IsSrgb(outputFormat))
        return Result::InvalidArgument;  // une UAV ne peut pas etre sRGB

    ID3D12GraphicsCommandList* cl = d.commandList;
    const uint32_t rw = desc_.renderWidth, rh = desc_.renderHeight;
    const uint32_t dw = desc_.displayWidth, dh = desc_.displayHeight;
    const bool reset = d.reset || frame_ == 0;
    const uint32_t cur = static_cast<uint32_t>(frame_ & 1);
    const uint32_t prev = cur ^ 1u;

    Constants c = {};
    c.renderSize[0] = rw;
    c.renderSize[1] = rh;
    c.displaySize[0] = dw;
    c.displaySize[1] = dh;
    c.jitter[0] = d.jitterX;
    c.jitter[1] = d.jitterY;
    c.motionScale[0] = d.motionScaleX;
    c.motionScale[1] = d.motionScaleY;
    c.depthP0 = d.depthP0;
    c.depthP1 = d.depthP1;
    c.exposure = d.exposure > 0.0f ? d.exposure : 1.0f;
    c.sharpness = Clamp(d.sharpness, 0.0f, 1.0f);
    c.flags = (reset ? kFlagReset : 0u) | (useNetwork_ ? kFlagNetwork : 0u) |
              (d.debugOutput ? kFlagDebug : 0u);
    // Meme calcul que core.sigma_sharp() cote reference.
    c.sigmaSharp = kSigmaSharpDisplay * Clamp(d.kernelWidth, 0.25f, 4.0f) *
                   static_cast<float>(rw) / static_cast<float>(dw);
    c.maxCount = Clamp(d.historyLength, 1.0f, 64.0f);
    c.clipGamma = Clamp(d.antiGhosting, 0.25f, 8.0f);
    c.netStrength = Clamp(d.networkStrength, 0.0f, 4.0f);

    // Tranche de descripteurs de cette image : 3 passes x (4 SRV + 3 UAV).
    const uint32_t base = static_cast<uint32_t>(
        frame_ % desc_.maxFramesInFlight) * kDescriptorsPerFrame;
    auto srv = [&](uint32_t pass, uint32_t i) {
        return base + pass * (kSrvCount + kUavCount) + i;
    };
    auto uav = [&](uint32_t pass, uint32_t i) {
        return base + pass * (kSrvCount + kUavCount) + kSrvCount + i;
    };

    // Passe 1
    WriteSrv(srv(0, 0), d.depth, ViewFormat(d.depth, d.depthFormat));
    WriteSrv(srv(0, 1), d.motionVectors,
             ViewFormat(d.motionVectors, d.motionFormat));
    WriteSrv(srv(0, 2), invZ_[prev].resource, DXGI_FORMAT_R32_FLOAT);
    WriteNullSrv(srv(0, 3));
    WriteUav(uav(0, 0), dilatedMotion_.resource, DXGI_FORMAT_R16G16_FLOAT);
    WriteUav(uav(0, 1), invZ_[cur].resource, DXGI_FORMAT_R32_FLOAT);
    WriteUav(uav(0, 2), disocclusion_.resource, DXGI_FORMAT_R8_UNORM);
    // Passe 2
    WriteSrv(srv(1, 0), d.color, ViewFormat(d.color, d.colorFormat));
    WriteSrv(srv(1, 1), dilatedMotion_.resource, DXGI_FORMAT_R16G16_FLOAT);
    WriteSrv(srv(1, 2), disocclusion_.resource, DXGI_FORMAT_R8_UNORM);
    WriteSrv(srv(1, 3), history_[prev].resource,
             DXGI_FORMAT_R16G16B16A16_FLOAT);
    WriteUav(uav(1, 0), history_[cur].resource,
             DXGI_FORMAT_R16G16B16A16_FLOAT);
    if (d.debugOutput)
        WriteUav(uav(1, 1), d.debugOutput,
                 ViewFormat(d.debugOutput, d.debugFormat));
    else
        WriteNullUav(uav(1, 1));
    WriteNullUav(uav(1, 2));
    // Passe 3
    WriteSrv(srv(2, 0), history_[cur].resource,
             DXGI_FORMAT_R16G16B16A16_FLOAT);
    WriteNullSrv(srv(2, 1));
    WriteNullSrv(srv(2, 2));
    WriteNullSrv(srv(2, 3));
    WriteUav(uav(2, 0), d.output, outputFormat);
    WriteNullUav(uav(2, 1));
    WriteNullUav(uav(2, 2));

    ID3D12DescriptorHeap* heaps[] = {heap_};
    cl->SetDescriptorHeaps(1, heaps);
    cl->SetComputeRootSignature(rootSignature_);
    cl->SetComputeRoot32BitConstants(kRootConstants, kRootConstantCount, &c,
                                     0);
    cl->SetComputeRootConstantBufferView(kRootNetwork,
                                         weights_->GetGPUVirtualAddress());

    const D3D12_RESOURCE_STATES kRead =
        D3D12_RESOURCE_STATE_NON_PIXEL_SHADER_RESOURCE;
    const D3D12_RESOURCE_STATES kWrite = D3D12_RESOURCE_STATE_UNORDERED_ACCESS;

    // --- Passe 1 : dilatation + desocclusion (resolution de rendu) -------
    Transition(cl, invZ_[prev], kRead);
    Transition(cl, invZ_[cur], kWrite);
    Transition(cl, dilatedMotion_, kWrite);
    Transition(cl, disocclusion_, kWrite);
    cl->SetPipelineState(prepare_);
    cl->SetComputeRootDescriptorTable(kRootSrvTable, Gpu(srv(0, 0)));
    cl->SetComputeRootDescriptorTable(kRootUavTable, Gpu(uav(0, 0)));
    cl->Dispatch((rw + 7) / 8, (rh + 7) / 8, 1);

    // --- Passe 2 : accumulation + reseau (resolution d'affichage) --------
    Transition(cl, dilatedMotion_, kRead);
    Transition(cl, disocclusion_, kRead);
    Transition(cl, history_[prev], kRead);
    Transition(cl, history_[cur], kWrite);
    cl->SetPipelineState(accumulate_);
    cl->SetComputeRootDescriptorTable(kRootSrvTable, Gpu(srv(1, 0)));
    cl->SetComputeRootDescriptorTable(kRootUavTable, Gpu(uav(1, 0)));
    cl->Dispatch((dw + 7) / 8, (dh + 7) / 8, 1);

    // --- Passe 3 : accentuation + sortie lineaire -------------------------
    Transition(cl, history_[cur], kRead);
    cl->SetPipelineState(sharpen_);
    cl->SetComputeRootDescriptorTable(kRootSrvTable, Gpu(srv(2, 0)));
    cl->SetComputeRootDescriptorTable(kRootUavTable, Gpu(uav(2, 0)));
    cl->Dispatch((dw + 7) / 8, (dh + 7) / 8, 1);

    // L'appelant lit la sortie ensuite : on attend la fin des ecritures.
    D3D12_RESOURCE_BARRIER b[2] = {};
    b[0].Type = D3D12_RESOURCE_BARRIER_TYPE_UAV;
    b[0].UAV.pResource = d.output;
    b[1].Type = D3D12_RESOURCE_BARRIER_TYPE_UAV;
    b[1].UAV.pResource = d.debugOutput;
    cl->ResourceBarrier(d.debugOutput ? 2 : 1, b);

    ++frame_;
    return Result::Ok;
}

// --- API publique ---------------------------------------------------------

Result CreateContext(const CreateDesc& desc, Context** outContext)
{
    if (!outContext || !desc.device || desc.renderWidth == 0 ||
        desc.renderHeight == 0 || desc.displayWidth < desc.renderWidth ||
        desc.displayHeight < desc.renderHeight)
        return Result::InvalidArgument;
    *outContext = nullptr;
    Context* ctx = new (std::nothrow) Context();
    if (!ctx)
        return Result::OutOfMemory;
    const Result r = ctx->Init(desc);
    if (r != Result::Ok) {
        ctx->Release();
        delete ctx;
        return r;
    }
    *outContext = ctx;
    return Result::Ok;
}

void DestroyContext(Context* context)
{
    if (!context)
        return;
    context->Release();
    delete context;
}

Result Dispatch(Context* context, const DispatchDesc& desc)
{
    return context ? context->Dispatch(desc) : Result::InvalidArgument;
}

Result SetWeights(Context* context, const float* weights, uint32_t count)
{
    return context ? context->SetWeights(weights, count)
                   : Result::InvalidArgument;
}

float GetUpscaleRatio(QualityMode mode)
{
    switch (mode) {
    case QualityMode::Native: return 1.0f;
    case QualityMode::Quality: return 1.5f;
    case QualityMode::Balanced: return 1.7f;
    case QualityMode::Performance: return 2.0f;
    case QualityMode::UltraPerformance: return 3.0f;
    }
    return 1.0f;
}

void GetRenderSize(QualityMode mode, uint32_t displayWidth,
                   uint32_t displayHeight, uint32_t* renderWidth,
                   uint32_t* renderHeight)
{
    const float ratio = GetUpscaleRatio(mode);
    const auto scale = [ratio](uint32_t v) {
        const uint32_t r = static_cast<uint32_t>(
            std::lround(static_cast<double>(v) / ratio));
        return r > 0 ? r : 1u;
    };
    if (renderWidth) *renderWidth = scale(displayWidth);
    if (renderHeight) *renderHeight = scale(displayHeight);
}

uint32_t GetJitterPhaseCount(uint32_t renderWidth, uint32_t displayWidth)
{
    const double ratio = static_cast<double>(displayWidth) /
                         static_cast<double>(renderWidth ? renderWidth : 1);
    const uint32_t n = static_cast<uint32_t>(std::ceil(8.0 * ratio * ratio));
    return n < 8 ? 8 : n;
}

static float Halton(uint32_t index, uint32_t base)
{
    float f = 1.0f, r = 0.0f;
    while (index > 0) {
        f /= static_cast<float>(base);
        r += f * static_cast<float>(index % base);
        index /= base;
    }
    return r;
}

void GetJitterOffset(uint32_t frameIndex, uint32_t phaseCount, float* x,
                     float* y)
{
    const uint32_t k = frameIndex % (phaseCount ? phaseCount : 1) + 1;
    if (x) *x = Halton(k, 2) - 0.5f;
    if (y) *y = Halton(k, 3) - 0.5f;
}

void GetDepthParams(float nearZ, float farZ, bool reversedZ, bool infiniteFar,
                    float* p0, float* p1)
{
    float a, b;
    if (reversedZ) {
        a = infiniteFar ? 1.0f / nearZ : (farZ - nearZ) / (nearZ * farZ);
        b = infiniteFar ? 0.0f : 1.0f / farZ;
    } else {
        a = infiniteFar ? -1.0f / nearZ : -(farZ - nearZ) / (nearZ * farZ);
        b = 1.0f / nearZ;
    }
    if (p0) *p0 = a;
    if (p1) *p1 = b;
}

} // namespace usr
