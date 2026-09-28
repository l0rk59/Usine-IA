// USR Universel -- implementation Direct3D 12 (PC et Xbox).
//
// Enchainement des passes par image (meme ordre que usr_ref/gpu.py,
// classe GpuUniversal, qui sert de modele et de test de parite) :
//
//   luma            image -> luminance (niveau 0) + luminance 16 bits (anneau)
//   down  x (L-1)   pyramide de luminance
//   grad  x L       gradients (servent a l'image SUIVANTE)
//   flow + median   du niveau le plus grossier au niveau 0 (si image prec.)
//   finalize        confiance, pixels fixes (HUD), zones immobiles
//   residual        erreur de prediction de l'historique (resolution rendu)
//   accumulate      retro-projection du residu + reseau (affichage)
//   output          RGB + accentuation RCAS -> sortie de l'appelant
//
// Une signature racine commune (USR_U_ROOT_SIGNATURE, embarquee dans le
// bytecode), un tas de descripteurs propre au contexte, decoupe en tranches
// par image en vol.

#include "usr/usr.h"

#include <cmath>
#include <cstring>
#include <new>

#include "usr_d3d12_util.h"
#include "usr_universal_weights.h"

#if !defined(USR_NO_BUILTIN_SHADERS)
#include "usr_universal_shaders.h"  // genere par CMake (dxc -Fh)
#endif

namespace usr {

using detail::Clamp;
using detail::IsSrgb;
using detail::SafeRelease;
using detail::Tracked;
using detail::ViewFormat;

namespace {

constexpr uint32_t kFlagReset = 1u;
constexpr uint32_t kFlagNetwork = 2u;
constexpr uint32_t kFlagDebug = 4u;
constexpr uint32_t kFlagTop = 8u;
constexpr uint32_t kFlagPeriod = 16u;
constexpr uint32_t kFlagPrev = 32u;

constexpr uint32_t kRootConstantCount = 20;
constexpr uint32_t kSrvCount = 8;   // t0..t7
constexpr uint32_t kUavCount = 4;   // u0..u3
constexpr uint32_t kSlotsPerPass = kSrvCount + kUavCount;
constexpr uint32_t kMaxLevels = 6;  // = flow.MAX_LEVELS
constexpr uint32_t kMinCoarseSide = 24;  // = flow.MIN_COARSE_SIDE
constexpr uint32_t kMaxPasses = 4 * kMaxLevels + 4;
constexpr uint32_t kDescriptorsPerFrame = kMaxPasses * kSlotsPerPass;
constexpr uint32_t kWeightFloats = 484;
constexpr uint32_t kWeightBufferSize = 2048;
constexpr uint32_t kPassCount = static_cast<uint32_t>(UniversalPass::Count);
// Au-dela, le test « meme phase » n'apporte plus rien (= flow.MAX_PERIOD).
constexpr uint32_t kMaxPeriod = 16;

enum RootParam : UINT {
    kRootConstants = 0,
    kRootNetwork = 1,
    kRootSrvTable = 2,
    kRootUavTable = 3,
};

// Doit suivre le cbuffer USRUConstants (shaders/usr_u_common.hlsli).
struct Constants {
    uint32_t renderSize[2];
    uint32_t displaySize[2];
    uint32_t levelSize[2];
    uint32_t parentSize[2];
    float jitter[2];
    float jitterDelta[2];
    uint32_t level;
    uint32_t flags;
    float netStrength;
    float maxCount;
    float boxT1;
    float sharpness;
    uint32_t reserved[2];
};
static_assert(sizeof(Constants) == kRootConstantCount * 4,
              "doit suivre le cbuffer USRUConstants");

// Meme regle que flow.level_count().
uint32_t LevelCount(uint32_t w, uint32_t h)
{
    uint32_t n = 1;
    const uint32_t m = w < h ? w : h;
    while ((m >> n) >= kMinCoarseSide && n < kMaxLevels)
        ++n;
    return n;
}

// Resources lues / ecrites par une passe (etats suivis).
struct PassIo {
    Tracked* reads[kSrvCount] = {};
    Tracked* writes[kUavCount] = {};
};

} // namespace

class UniversalContext {
public:
    Result Init(const UniversalCreateDesc& desc);
    void Release();
    Result Dispatch(const UniversalDispatchDesc& desc);
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
    // Enregistre une passe : descripteurs, transitions, dispatch.
    void Run(ID3D12GraphicsCommandList* cl, UniversalPass pass,
             const Constants& c, uint32_t threadsX, uint32_t threadsY,
             ID3D12Resource* const srv[kSrvCount],
             const DXGI_FORMAT srvFormat[kSrvCount],
             ID3D12Resource* const uav[kUavCount],
             const DXGI_FORMAT uavFormat[kUavCount], const PassIo& io);

    UniversalCreateDesc desc_ = {};
    ID3D12Device* device_ = nullptr;
    ID3D12RootSignature* rootSignature_ = nullptr;
    ID3D12PipelineState* pipelines_[kPassCount] = {};
    ID3D12DescriptorHeap* heap_ = nullptr;
    UINT descriptorSize_ = 0;
    ID3D12Resource* weights_ = nullptr;
    void* weightsMapped_ = nullptr;

    uint32_t levels_ = 1;
    uint32_t levelW_[kMaxLevels] = {};
    uint32_t levelH_[kMaxLevels] = {};
    Tracked luma_[2][kMaxLevels];
    Tracked grad_[2][kMaxLevels];
    Tracked motionRaw_[kMaxLevels];
    Tracked motionMed_[kMaxLevels];
    Tracked ring_[kMaxPeriod + 1];  // luminances 16 bits : periode + 1
    uint32_t ringSize_ = 2;
    Tracked final_[2];
    Tracked aux_;
    Tracked residual_;
    Tracked history_[2];

    uint64_t frame_ = 0;      // images depuis la derniere remise a zero
    uint64_t total_ = 0;      // images depuis la creation
    uint32_t passIndex_ = 0;  // passe courante dans la tranche de l'image
    uint32_t sliceBase_ = 0;
    float prevJitter_[2] = {0.0f, 0.0f};
    bool useNetwork_ = true;
};

// --------------------------------------------------------------------------

Result UniversalContext::Init(const UniversalCreateDesc& desc)
{
    desc_ = desc;
    device_ = desc.device;
    device_->AddRef();
    useNetwork_ = (desc.flags & kCreateDisableNetwork) == 0;
    if (desc_.maxFramesInFlight == 0)
        desc_.maxFramesInFlight = 1;
    if (desc_.jitterPeriod > kMaxPeriod || desc_.jitterPeriod == 1)
        desc_.jitterPeriod = 0;

    ShaderBytecode code[kPassCount];
    for (uint32_t i = 0; i < kPassCount; ++i)
        code[i] = desc.shaders[i];
#if !defined(USR_NO_BUILTIN_SHADERS)
    const ShaderBytecode builtin[kPassCount] = {
        {g_usr_u_luma, sizeof(g_usr_u_luma)},
        {g_usr_u_down, sizeof(g_usr_u_down)},
        {g_usr_u_grad, sizeof(g_usr_u_grad)},
        {g_usr_u_flow, sizeof(g_usr_u_flow)},
        {g_usr_u_median, sizeof(g_usr_u_median)},
        {g_usr_u_finalize, sizeof(g_usr_u_finalize)},
        {g_usr_u_residual, sizeof(g_usr_u_residual)},
        {g_usr_u_accumulate, sizeof(g_usr_u_accumulate)},
        {g_usr_u_output, sizeof(g_usr_u_output)},
    };
    for (uint32_t i = 0; i < kPassCount; ++i)
        if (!code[i].data)
            code[i] = builtin[i];
#endif
    for (uint32_t i = 0; i < kPassCount; ++i)
        if (!code[i].data)
            return Result::InvalidArgument;

    if (FAILED(device_->CreateRootSignature(0, code[0].data, code[0].size,
                                            IID_PPV_ARGS(&rootSignature_))))
        return Result::DeviceError;
    Result r;
    for (uint32_t i = 0; i < kPassCount; ++i)
        if ((r = CreatePipeline(code[i], &pipelines_[i])) != Result::Ok)
            return r;

    D3D12_DESCRIPTOR_HEAP_DESC hd = {};
    hd.Type = D3D12_DESCRIPTOR_HEAP_TYPE_CBV_SRV_UAV;
    hd.NumDescriptors = kDescriptorsPerFrame * desc_.maxFramesInFlight;
    hd.Flags = D3D12_DESCRIPTOR_HEAP_FLAG_SHADER_VISIBLE;
    if (FAILED(device_->CreateDescriptorHeap(&hd, IID_PPV_ARGS(&heap_))))
        return Result::OutOfMemory;
    descriptorSize_ = device_->GetDescriptorHandleIncrementSize(hd.Type);

    const uint32_t rw = desc.renderWidth, rh = desc.renderHeight;
    const uint32_t dw = desc.displayWidth, dh = desc.displayHeight;
    levels_ = LevelCount(rw, rh);
    levelW_[0] = rw;
    levelH_[0] = rh;
    for (uint32_t k = 1; k < levels_; ++k) {
        levelW_[k] = (levelW_[k - 1] + 1) / 2;
        levelH_[k] = (levelH_[k - 1] + 1) / 2;
    }
    for (uint32_t b = 0; b < 2; ++b) {
        for (uint32_t k = 0; k < levels_; ++k) {
            if ((r = CreateTexture(levelW_[k], levelH_[k],
                                   DXGI_FORMAT_R32_FLOAT, &luma_[b][k])) !=
                Result::Ok) return r;
            if ((r = CreateTexture(levelW_[k], levelH_[k],
                                   DXGI_FORMAT_R32G32_FLOAT, &grad_[b][k])) !=
                Result::Ok) return r;
        }
        if ((r = CreateTexture(rw, rh, DXGI_FORMAT_R32G32_FLOAT,
                               &final_[b])) != Result::Ok) return r;
        if ((r = CreateTexture(dw, dh, DXGI_FORMAT_R16G16B16A16_FLOAT,
                               &history_[b])) != Result::Ok) return r;
    }
    for (uint32_t k = 0; k < levels_; ++k) {
        if ((r = CreateTexture(levelW_[k], levelH_[k],
                               DXGI_FORMAT_R32G32_FLOAT, &motionRaw_[k])) !=
            Result::Ok) return r;
        if ((r = CreateTexture(levelW_[k], levelH_[k],
                               DXGI_FORMAT_R32G32_FLOAT, &motionMed_[k])) !=
            Result::Ok) return r;
    }
    ringSize_ = (desc_.jitterPeriod ? desc_.jitterPeriod : 1) + 1;
    for (uint32_t i = 0; i < ringSize_; ++i)
        if ((r = CreateTexture(rw, rh, DXGI_FORMAT_R16_UINT, &ring_[i])) !=
            Result::Ok) return r;
    if ((r = CreateTexture(rw, rh, DXGI_FORMAT_R8G8B8A8_UNORM, &aux_)) !=
        Result::Ok) return r;
    if ((r = CreateTexture(rw, rh, DXGI_FORMAT_R16G16B16A16_FLOAT,
                           &residual_)) != Result::Ok) return r;

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
    return SetWeights(detail::kUniversalWeights,
                      detail::kUniversalWeightCount);
}

void UniversalContext::Release()
{
    if (weights_ && weightsMapped_)
        weights_->Unmap(0, nullptr);
    SafeRelease(weights_);
    for (Tracked& t : history_) SafeRelease(t.resource);
    SafeRelease(residual_.resource);
    SafeRelease(aux_.resource);
    for (Tracked& t : final_) SafeRelease(t.resource);
    for (Tracked& t : ring_) SafeRelease(t.resource);
    for (uint32_t k = 0; k < kMaxLevels; ++k) {
        SafeRelease(motionRaw_[k].resource);
        SafeRelease(motionMed_[k].resource);
        for (uint32_t b = 0; b < 2; ++b) {
            SafeRelease(luma_[b][k].resource);
            SafeRelease(grad_[b][k].resource);
        }
    }
    SafeRelease(heap_);
    for (ID3D12PipelineState*& p : pipelines_) SafeRelease(p);
    SafeRelease(rootSignature_);
    SafeRelease(device_);
}

Result UniversalContext::SetWeights(const float* weights, uint32_t count)
{
    if (!weights || count < 482 || count > kWeightFloats)
        return Result::InvalidArgument;
    std::memset(weightsMapped_, 0, kWeightFloats * sizeof(float));
    std::memcpy(weightsMapped_, weights, count * sizeof(float));
    return Result::Ok;
}

Result UniversalContext::CreateTexture(uint32_t w, uint32_t h,
                                       DXGI_FORMAT format, Tracked* out)
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

Result UniversalContext::CreatePipeline(const ShaderBytecode& cs,
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

void UniversalContext::Transition(ID3D12GraphicsCommandList* cl, Tracked& t,
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

D3D12_CPU_DESCRIPTOR_HANDLE UniversalContext::Cpu(uint32_t index) const
{
    D3D12_CPU_DESCRIPTOR_HANDLE h = heap_->GetCPUDescriptorHandleForHeapStart();
    h.ptr += static_cast<SIZE_T>(index) * descriptorSize_;
    return h;
}

D3D12_GPU_DESCRIPTOR_HANDLE UniversalContext::Gpu(uint32_t index) const
{
    D3D12_GPU_DESCRIPTOR_HANDLE h = heap_->GetGPUDescriptorHandleForHeapStart();
    h.ptr += static_cast<UINT64>(index) * descriptorSize_;
    return h;
}

void UniversalContext::WriteSrv(uint32_t slot, ID3D12Resource* r,
                                DXGI_FORMAT format)
{
    D3D12_SHADER_RESOURCE_VIEW_DESC d = {};
    d.Format = format;
    d.ViewDimension = D3D12_SRV_DIMENSION_TEXTURE2D;
    d.Shader4ComponentMapping = D3D12_DEFAULT_SHADER_4_COMPONENT_MAPPING;
    d.Texture2D.MipLevels = 1;
    device_->CreateShaderResourceView(r, &d, Cpu(slot));
}

void UniversalContext::WriteUav(uint32_t slot, ID3D12Resource* r,
                                DXGI_FORMAT format)
{
    D3D12_UNORDERED_ACCESS_VIEW_DESC d = {};
    d.Format = format;
    d.ViewDimension = D3D12_UAV_DIMENSION_TEXTURE2D;
    device_->CreateUnorderedAccessView(r, nullptr, &d, Cpu(slot));
}

void UniversalContext::Run(ID3D12GraphicsCommandList* cl, UniversalPass pass,
                           const Constants& c, uint32_t threadsX,
                           uint32_t threadsY,
                           ID3D12Resource* const srv[kSrvCount],
                           const DXGI_FORMAT srvFormat[kSrvCount],
                           ID3D12Resource* const uav[kUavCount],
                           const DXGI_FORMAT uavFormat[kUavCount],
                           const PassIo& io)
{
    const uint32_t base = sliceBase_ + passIndex_ * kSlotsPerPass;
    ++passIndex_;
    for (uint32_t i = 0; i < kSrvCount; ++i)
        WriteSrv(base + i, srv[i],
                 srv[i] ? srvFormat[i] : DXGI_FORMAT_R32_FLOAT);
    for (uint32_t i = 0; i < kUavCount; ++i)
        WriteUav(base + kSrvCount + i, uav[i],
                 uav[i] ? uavFormat[i] : DXGI_FORMAT_R32_FLOAT);
    for (Tracked* t : io.reads)
        if (t)
            Transition(cl, *t, D3D12_RESOURCE_STATE_NON_PIXEL_SHADER_RESOURCE);
    for (Tracked* t : io.writes)
        if (t)
            Transition(cl, *t, D3D12_RESOURCE_STATE_UNORDERED_ACCESS);
    cl->SetPipelineState(pipelines_[static_cast<uint32_t>(pass)]);
    cl->SetComputeRoot32BitConstants(kRootConstants, kRootConstantCount, &c,
                                     0);
    cl->SetComputeRootDescriptorTable(kRootSrvTable, Gpu(base));
    cl->SetComputeRootDescriptorTable(kRootUavTable, Gpu(base + kSrvCount));
    cl->Dispatch((threadsX + 7) / 8, (threadsY + 7) / 8, 1);
}

Result UniversalContext::Dispatch(const UniversalDispatchDesc& d)
{
    if (!d.commandList || !d.color || !d.output)
        return Result::InvalidArgument;
    const DXGI_FORMAT colorFormat = ViewFormat(d.color, d.colorFormat);
    const DXGI_FORMAT outputFormat = ViewFormat(d.output, d.outputFormat);
    if (IsSrgb(outputFormat))
        return Result::InvalidArgument;  // une UAV ne peut pas etre sRGB
    const DXGI_FORMAT debugFormat =
        d.debugOutput ? ViewFormat(d.debugOutput, d.debugFormat)
                      : DXGI_FORMAT_UNKNOWN;

    ID3D12GraphicsCommandList* cl = d.commandList;
    const uint32_t rw = desc_.renderWidth, rh = desc_.renderHeight;
    const uint32_t dw = desc_.displayWidth, dh = desc_.displayHeight;
    if (d.reset)
        frame_ = 0;
    const uint64_t n = frame_;
    const uint32_t cur = static_cast<uint32_t>(total_ & 1);
    const uint32_t prev = cur ^ 1u;
    const bool hasPrev = n >= 1;
    const uint32_t period = desc_.jitterPeriod;
    const uint32_t K = ringSize_;
    Tracked& ringCur = ring_[n % K];
    Tracked& ringPrev = ring_[(n + K - 1) % K];
    Tracked& ringPhase = ring_[(n + K - (period ? period : 1)) % K];

    Constants c = {};
    c.renderSize[0] = rw;
    c.renderSize[1] = rh;
    c.displaySize[0] = dw;
    c.displaySize[1] = dh;
    c.jitter[0] = d.jitterX;
    c.jitter[1] = d.jitterY;
    if (hasPrev) {
        // Difference calculee en double, comme la reference.
        c.jitterDelta[0] = static_cast<float>(
            static_cast<double>(d.jitterX) - prevJitter_[0]);
        c.jitterDelta[1] = static_cast<float>(
            static_cast<double>(d.jitterY) - prevJitter_[1]);
    }
    c.netStrength = Clamp(d.networkStrength, 0.0f, 4.0f);
    c.maxCount = Clamp(d.historyLength, 1.0f, 64.0f);
    c.boxT1 = Clamp(d.antiGhosting, 0.05f, 4.0f);
    c.sharpness = Clamp(d.sharpness, 0.0f, 1.0f);

    sliceBase_ = static_cast<uint32_t>(
        total_ % desc_.maxFramesInFlight) * kDescriptorsPerFrame;
    passIndex_ = 0;

    ID3D12DescriptorHeap* heaps[] = {heap_};
    cl->SetDescriptorHeaps(1, heaps);
    cl->SetComputeRootSignature(rootSignature_);
    cl->SetComputeRootConstantBufferView(kRootNetwork,
                                         weights_->GetGPUVirtualAddress());

    const DXGI_FORMAT R32 = DXGI_FORMAT_R32_FLOAT;
    const DXGI_FORMAT RG32 = DXGI_FORMAT_R32G32_FLOAT;
    const DXGI_FORMAT R16U = DXGI_FORMAT_R16_UINT;
    const DXGI_FORMAT RGBA8 = DXGI_FORMAT_R8G8B8A8_UNORM;
    const DXGI_FORMAT RGBA16 = DXGI_FORMAT_R16G16B16A16_FLOAT;
    // L'image de l'appelant : on suit son etat (lecture) sans le changer.
    Tracked colorIn = {d.color,
                       D3D12_RESOURCE_STATE_NON_PIXEL_SHADER_RESOURCE};

    // --- luminance ------------------------------------------------------------
    {
        Constants k = c;
        ID3D12Resource* s[kSrvCount] = {d.color};
        DXGI_FORMAT sf[kSrvCount] = {colorFormat};
        ID3D12Resource* u[kUavCount] = {luma_[cur][0].resource,
                                        ringCur.resource};
        DXGI_FORMAT uf[kUavCount] = {R32, R16U};
        PassIo io;
        io.writes[0] = &luma_[cur][0];
        io.writes[1] = &ringCur;
        Run(cl, UniversalPass::Luma, k, rw, rh, s, sf, u, uf, io);
    }
    for (uint32_t lv = 0; lv + 1 < levels_; ++lv) {
        Constants k = c;
        k.levelSize[0] = levelW_[lv];
        k.levelSize[1] = levelH_[lv];
        k.level = lv;
        ID3D12Resource* s[kSrvCount] = {luma_[cur][lv].resource};
        DXGI_FORMAT sf[kSrvCount] = {R32};
        ID3D12Resource* u[kUavCount] = {luma_[cur][lv + 1].resource};
        DXGI_FORMAT uf[kUavCount] = {R32};
        PassIo io;
        io.reads[0] = &luma_[cur][lv];
        io.writes[0] = &luma_[cur][lv + 1];
        Run(cl, UniversalPass::Down, k, levelW_[lv + 1], levelH_[lv + 1], s,
            sf, u, uf, io);
    }
    for (uint32_t lv = 0; lv < levels_; ++lv) {
        Constants k = c;
        k.levelSize[0] = levelW_[lv];
        k.levelSize[1] = levelH_[lv];
        k.level = lv;
        ID3D12Resource* s[kSrvCount] = {luma_[cur][lv].resource};
        DXGI_FORMAT sf[kSrvCount] = {R32};
        ID3D12Resource* u[kUavCount] = {grad_[cur][lv].resource};
        DXGI_FORMAT uf[kUavCount] = {RG32};
        PassIo io;
        io.reads[0] = &luma_[cur][lv];
        io.writes[0] = &grad_[cur][lv];
        Run(cl, UniversalPass::Gradient, k, levelW_[lv], levelH_[lv], s, sf,
            u, uf, io);
    }

    // --- flot, du niveau grossier au niveau 0 ---------------------------------
    if (hasPrev) {
        for (uint32_t i = levels_; i-- > 0;) {
            const bool top = i + 1 == levels_;
            Constants k = c;
            k.levelSize[0] = levelW_[i];
            k.levelSize[1] = levelH_[i];
            const uint32_t pi = top ? i : i + 1;
            k.parentSize[0] = levelW_[pi];
            k.parentSize[1] = levelH_[pi];
            k.level = i;
            k.flags = top ? kFlagTop : 0u;
            Tracked* parent = top ? nullptr : &motionMed_[i + 1];
            {
                ID3D12Resource* s[kSrvCount] = {
                    luma_[cur][i].resource, luma_[prev][i].resource,
                    grad_[prev][i].resource,
                    parent ? parent->resource : nullptr,
                    final_[prev].resource};
                DXGI_FORMAT sf[kSrvCount] = {R32, R32, RG32, RG32, RG32};
                ID3D12Resource* u[kUavCount] = {motionRaw_[i].resource};
                DXGI_FORMAT uf[kUavCount] = {RG32};
                PassIo io;
                io.reads[0] = &luma_[cur][i];
                io.reads[1] = &luma_[prev][i];
                io.reads[2] = &grad_[prev][i];
                io.reads[3] = parent;
                io.reads[4] = &final_[prev];
                io.writes[0] = &motionRaw_[i];
                Run(cl, UniversalPass::Flow, k, levelW_[i], levelH_[i], s, sf,
                    u, uf, io);
            }
            {
                k.flags = 0u;
                ID3D12Resource* s[kSrvCount] = {motionRaw_[i].resource};
                DXGI_FORMAT sf[kSrvCount] = {RG32};
                ID3D12Resource* u[kUavCount] = {motionMed_[i].resource};
                DXGI_FORMAT uf[kUavCount] = {RG32};
                PassIo io;
                io.reads[0] = &motionRaw_[i];
                io.writes[0] = &motionMed_[i];
                Run(cl, UniversalPass::Median, k, levelW_[i], levelH_[i], s,
                    sf, u, uf, io);
            }
        }
    }
    {
        Constants k = c;
        k.flags = (hasPrev ? kFlagPrev : 0u) |
                  (period && n >= period ? kFlagPeriod : 0u);
        ID3D12Resource* s[kSrvCount] = {
            luma_[cur][0].resource,
            hasPrev ? luma_[prev][0].resource : nullptr,
            hasPrev ? motionMed_[0].resource : nullptr,
            ringCur.resource,
            hasPrev ? ringPrev.resource : nullptr,
            (k.flags & kFlagPeriod) ? ringPhase.resource : nullptr};
        DXGI_FORMAT sf[kSrvCount] = {R32, R32, RG32, R16U, R16U, R16U};
        ID3D12Resource* u[kUavCount] = {final_[cur].resource, aux_.resource};
        DXGI_FORMAT uf[kUavCount] = {RG32, RGBA8};
        PassIo io;
        io.reads[0] = &luma_[cur][0];
        io.reads[1] = hasPrev ? &luma_[prev][0] : nullptr;
        io.reads[2] = hasPrev ? &motionMed_[0] : nullptr;
        io.reads[3] = &ringCur;
        io.reads[4] = hasPrev ? &ringPrev : nullptr;
        io.reads[5] = (k.flags & kFlagPeriod) ? &ringPhase : nullptr;
        io.writes[0] = &final_[cur];
        io.writes[1] = &aux_;
        Run(cl, UniversalPass::Finalize, k, rw, rh, s, sf, u, uf, io);
    }

    // --- residu, accumulation, sortie -------------------------------------
    const bool first = n == 0;
    const uint32_t accFlags = (first ? kFlagReset : 0u) |
                              (useNetwork_ ? kFlagNetwork : 0u) |
                              (d.debugOutput ? kFlagDebug : 0u);
    {
        Constants k = c;
        k.flags = accFlags;
        ID3D12Resource* s[kSrvCount] = {d.color, final_[cur].resource,
                                        aux_.resource,
                                        history_[prev].resource};
        DXGI_FORMAT sf[kSrvCount] = {colorFormat, RG32, RGBA8, RGBA16};
        ID3D12Resource* u[kUavCount] = {residual_.resource};
        DXGI_FORMAT uf[kUavCount] = {RGBA16};
        PassIo io;
        io.reads[0] = &colorIn;
        io.reads[1] = &final_[cur];
        io.reads[2] = &aux_;
        io.reads[3] = &history_[prev];
        io.writes[0] = &residual_;
        Run(cl, UniversalPass::Residual, k, rw, rh, s, sf, u, uf, io);
    }
    {
        Constants k = c;
        k.flags = accFlags;
        ID3D12Resource* s[kSrvCount] = {
            d.color, final_[cur].resource, aux_.resource,
            history_[prev].resource, residual_.resource};
        DXGI_FORMAT sf[kSrvCount] = {colorFormat, RG32, RGBA8, RGBA16,
                                     RGBA16};
        ID3D12Resource* u[kUavCount] = {history_[cur].resource,
                                        d.debugOutput};
        DXGI_FORMAT uf[kUavCount] = {RGBA16, debugFormat};
        PassIo io;
        io.reads[0] = &colorIn;
        io.reads[1] = &final_[cur];
        io.reads[2] = &aux_;
        io.reads[3] = &history_[prev];
        io.reads[4] = &residual_;
        io.writes[0] = &history_[cur];
        Run(cl, UniversalPass::Accumulate, k, dw, dh, s, sf, u, uf, io);
    }
    {
        Constants k = c;
        k.flags = accFlags;
        ID3D12Resource* s[kSrvCount] = {history_[cur].resource};
        DXGI_FORMAT sf[kSrvCount] = {RGBA16};
        ID3D12Resource* u[kUavCount] = {d.output};
        DXGI_FORMAT uf[kUavCount] = {outputFormat};
        PassIo io;
        io.reads[0] = &history_[cur];
        Run(cl, UniversalPass::Output, k, dw, dh, s, sf, u, uf, io);
    }

    // L'appelant lit la sortie ensuite : on attend la fin des ecritures.
    D3D12_RESOURCE_BARRIER b[2] = {};
    b[0].Type = D3D12_RESOURCE_BARRIER_TYPE_UAV;
    b[0].UAV.pResource = d.output;
    b[1].Type = D3D12_RESOURCE_BARRIER_TYPE_UAV;
    b[1].UAV.pResource = d.debugOutput;
    cl->ResourceBarrier(d.debugOutput ? 2 : 1, b);

    prevJitter_[0] = d.jitterX;
    prevJitter_[1] = d.jitterY;
    ++frame_;
    ++total_;
    return Result::Ok;
}

// --- API publique ---------------------------------------------------------

Result CreateUniversalContext(const UniversalCreateDesc& desc,
                              UniversalContext** outContext)
{
    if (!outContext || !desc.device || desc.renderWidth < 8 ||
        desc.renderHeight < 8 || desc.displayWidth < desc.renderWidth ||
        desc.displayHeight < desc.renderHeight)
        return Result::InvalidArgument;
    *outContext = nullptr;
    UniversalContext* ctx = new (std::nothrow) UniversalContext();
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

void DestroyUniversalContext(UniversalContext* context)
{
    if (!context)
        return;
    context->Release();
    delete context;
}

Result DispatchUniversal(UniversalContext* context,
                         const UniversalDispatchDesc& desc)
{
    return context ? context->Dispatch(desc) : Result::InvalidArgument;
}

Result SetUniversalWeights(UniversalContext* context, const float* weights,
                           uint32_t count)
{
    return context ? context->SetWeights(weights, count)
                   : Result::InvalidArgument;
}

// Meme table que universel.GRID_ORDER.
static const uint8_t kGrid2[4][2] = {{0, 0}, {1, 1}, {1, 0}, {0, 1}};
static const uint8_t kGrid3[9][2] = {{0, 0}, {1, 2}, {2, 1}, {2, 0}, {0, 2},
                                     {1, 1}, {2, 2}, {0, 1}, {1, 0}};

static uint32_t GridFactor(uint32_t rw, uint32_t rh, uint32_t dw,
                           uint32_t dh)
{
    for (uint32_t n = 2; n <= 3; ++n)
        if (dw == n * rw && dh == n * rh)
            return n;
    return 0;
}

uint32_t GetUniversalJitterPeriod(uint32_t renderWidth, uint32_t renderHeight,
                                  uint32_t displayWidth,
                                  uint32_t displayHeight)
{
    const uint32_t n =
        GridFactor(renderWidth, renderHeight, displayWidth, displayHeight);
    if (n)
        return n * n;
    return GetJitterPhaseCount(renderWidth, displayWidth);
}

void GetUniversalJitter(uint32_t frameIndex, uint32_t renderWidth,
                        uint32_t renderHeight, uint32_t displayWidth,
                        uint32_t displayHeight, float* x, float* y)
{
    const uint32_t n =
        GridFactor(renderWidth, renderHeight, displayWidth, displayHeight);
    if (n) {
        const uint8_t* cell =
            n == 2 ? kGrid2[frameIndex % 4] : kGrid3[frameIndex % 9];
        if (x) *x = (cell[0] + 0.5f) / static_cast<float>(n) - 0.5f;
        if (y) *y = (cell[1] + 0.5f) / static_cast<float>(n) - 0.5f;
        return;
    }
    GetJitterOffset(frameIndex,
                    GetJitterPhaseCount(renderWidth, displayWidth), x, y);
}

} // namespace usr
