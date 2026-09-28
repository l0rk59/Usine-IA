// USR Labo -- la boucle d'images Direct3D 12 commune au PC et a la Xbox :
// file de commandes, allocateurs par image en vol, cloture (fence), et
// copie de l'image finale dans la chaine d'echange.

#pragma once

#include <cstdint>
#include <string>

#include "usr/usr.h"  // d3d12.h ou d3d12_x(s).h selon la plateforme

namespace labo {

class FrameLoop {
public:
    FrameLoop() = default;
    ~FrameLoop();
    FrameLoop(const FrameLoop&) = delete;
    FrameLoop& operator=(const FrameLoop&) = delete;

    bool Init(ID3D12Device* device, uint32_t framesInFlight, std::string* error);
    void Shutdown();

    ID3D12CommandQueue* queue() const { return queue_; }
    uint32_t framesInFlight() const { return count_; }

    // Attend que la tranche suivante soit libre et ouvre sa liste.
    ID3D12GraphicsCommandList* Begin(uint32_t* slot);
    // Copie src (etat COPY_SOURCE) dans le tampon d'arriere-plan (PRESENT).
    void CopyToBackBuffer(ID3D12Resource* src, ID3D12Resource* backBuffer);
    // Ferme, soumet et signale la cloture de la tranche.
    bool Submit();
    // Attend que tout le travail soumis soit termine.
    void WaitIdle();

private:
    void WaitFor(uint64_t value);

    static constexpr uint32_t kMax = 4;
    ID3D12Device* device_ = nullptr;
    ID3D12CommandQueue* queue_ = nullptr;
    ID3D12CommandAllocator* allocators_[kMax] = {};
    ID3D12GraphicsCommandList* list_ = nullptr;
    ID3D12Fence* fence_ = nullptr;
    void* event_ = nullptr;
    uint64_t slotValues_[kMax] = {};
    uint64_t nextValue_ = 1;
    uint32_t count_ = 0;
    uint32_t slot_ = 0;
};

} // namespace labo
