#include "labo_frame.h"

namespace labo {

namespace {

template <typename T>
void SafeRelease(T*& p)
{
    if (p) {
        p->Release();
        p = nullptr;
    }
}

} // namespace

FrameLoop::~FrameLoop()
{
    Shutdown();
}

bool FrameLoop::Init(ID3D12Device* device, uint32_t framesInFlight,
                     std::string* error)
{
    auto fail = [error](const char* what) {
        if (error)
            *error = what;
        return false;
    };
    if (!device || framesInFlight == 0 || framesInFlight > kMax)
        return fail("parametres invalides");
    device_ = device;
    device_->AddRef();
    count_ = framesInFlight;

    D3D12_COMMAND_QUEUE_DESC qd = {};
    qd.Type = D3D12_COMMAND_LIST_TYPE_DIRECT;
    if (FAILED(device_->CreateCommandQueue(&qd, IID_PPV_ARGS(&queue_))))
        return fail("file de commandes");
    for (uint32_t i = 0; i < count_; ++i)
        if (FAILED(device_->CreateCommandAllocator(
                D3D12_COMMAND_LIST_TYPE_DIRECT, IID_PPV_ARGS(&allocators_[i]))))
            return fail("allocateur de commandes");
    if (FAILED(device_->CreateCommandList(0, D3D12_COMMAND_LIST_TYPE_DIRECT,
                                          allocators_[0], nullptr,
                                          IID_PPV_ARGS(&list_))))
        return fail("liste de commandes");
    list_->Close();
    if (FAILED(device_->CreateFence(0, D3D12_FENCE_FLAG_NONE,
                                    IID_PPV_ARGS(&fence_))))
        return fail("cloture");
    event_ = CreateEventEx(nullptr, nullptr, 0, EVENT_ALL_ACCESS);
    if (!event_)
        return fail("evenement de cloture");
    return true;
}

void FrameLoop::Shutdown()
{
    if (queue_ && fence_)
        WaitIdle();
    if (event_) {
        CloseHandle(static_cast<HANDLE>(event_));
        event_ = nullptr;
    }
    SafeRelease(fence_);
    SafeRelease(list_);
    for (auto& a : allocators_)
        SafeRelease(a);
    SafeRelease(queue_);
    SafeRelease(device_);
}

void FrameLoop::WaitFor(uint64_t value)
{
    if (fence_->GetCompletedValue() >= value)
        return;
    fence_->SetEventOnCompletion(value, static_cast<HANDLE>(event_));
    WaitForSingleObjectEx(static_cast<HANDLE>(event_), INFINITE, FALSE);
}

ID3D12GraphicsCommandList* FrameLoop::Begin(uint32_t* slot)
{
    WaitFor(slotValues_[slot_]);
    allocators_[slot_]->Reset();
    list_->Reset(allocators_[slot_], nullptr);
    if (slot)
        *slot = slot_;
    return list_;
}

void FrameLoop::CopyToBackBuffer(ID3D12Resource* src, ID3D12Resource* backBuffer)
{
    D3D12_RESOURCE_BARRIER b = {};
    b.Type = D3D12_RESOURCE_BARRIER_TYPE_TRANSITION;
    b.Transition.pResource = backBuffer;
    b.Transition.Subresource = D3D12_RESOURCE_BARRIER_ALL_SUBRESOURCES;
    b.Transition.StateBefore = D3D12_RESOURCE_STATE_PRESENT;
    b.Transition.StateAfter = D3D12_RESOURCE_STATE_COPY_DEST;
    list_->ResourceBarrier(1, &b);
    list_->CopyResource(backBuffer, src);
    b.Transition.StateBefore = D3D12_RESOURCE_STATE_COPY_DEST;
    b.Transition.StateAfter = D3D12_RESOURCE_STATE_PRESENT;
    list_->ResourceBarrier(1, &b);
}

bool FrameLoop::Submit()
{
    if (FAILED(list_->Close()))
        return false;
    ID3D12CommandList* lists[] = {list_};
    queue_->ExecuteCommandLists(1, lists);
    slotValues_[slot_] = nextValue_;
    queue_->Signal(fence_, nextValue_++);
    slot_ = (slot_ + 1) % count_;
    return true;
}

void FrameLoop::WaitIdle()
{
    const uint64_t value = nextValue_++;
    queue_->Signal(fence_, value);
    WaitFor(value);
}

} // namespace labo
