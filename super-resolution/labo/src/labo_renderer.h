// USR Labo -- moteur de rendu Direct3D 12, commun a la Xbox (UWP) et au PC.
//
// Chaque image : la scene de test est rendue comme par un jeu (basse
// resolution, jitter, profondeur, mouvement), passe dans USR (avec et
// sans IA), et les vues choisies sont composees a l'ecran avec le menu.
// La couche plateforme ne fait que fournir le peripherique, la file de
// commandes, la manette, et copier Output() dans la chaine d'echange.

#pragma once

#include <cstdint>
#include <functional>
#include <string>
#include <vector>

#include "usr/usr.h"

#include "labo_core.h"

namespace labo {

struct RendererDesc {
    ID3D12Device* device = nullptr;
    ID3D12CommandQueue* queue = nullptr;   // pour la frequence des chronos
    uint32_t displayWidth = 0;
    uint32_t displayHeight = 0;
    uint32_t framesInFlight = 2;           // tranches de ressources par image
    std::string deviceName;                // affiche dans les mesures
    // Attend que le GPU ait fini tout le travail soumis (changement de
    // resolution de rendu ou de modele : on recree des ressources).
    std::function<void()> waitForGpu;
};

// Copie CPU d'une image (tests automatiques, captures d'ecran).
struct Capture {
    uint32_t displayW = 0, displayH = 0, renderW = 0, renderH = 0;
    float jitter[2] = {0, 0};
    std::vector<uint8_t> composed;      // RGBA8, affichage
    std::vector<uint16_t> usrIA;        // RGBA16F, affichage (sortie USR + IA)
    std::vector<uint16_t> sceneColor;   // RGBA16F, rendu (entree de USR)
    std::vector<float> sceneDepth;      // R32F, rendu
    std::vector<uint16_t> sceneMotion;  // RG16F, rendu (pixels)
};

class Renderer {
public:
    Renderer();
    ~Renderer();
    Renderer(const Renderer&) = delete;
    Renderer& operator=(const Renderer&) = delete;

    bool Init(const RendererDesc& desc, std::string* error);
    // Le GPU ne doit plus rien executer (attendre avant).
    void Shutdown();

    // Enregistre une image dans cl, avec la tranche slot (0 .. framesInFlight-1)
    // dont le travail precedent doit etre termine. A la fin, Output() est
    // dans l'etat COPY_SOURCE.
    bool Record(ID3D12GraphicsCommandList* cl, Controller& ctrl, uint32_t slot,
                double dt);
    ID3D12Resource* Output() const;
    const Stats& stats() const;

    // Capture : RecordCapture juste apres Record (meme liste), puis
    // ReadCapture une fois la liste executee et terminee.
    void RecordCapture(ID3D12GraphicsCommandList* cl);
    bool ReadCapture(Capture* out);

private:
    struct Impl;
    Impl* impl_;
};

} // namespace labo
