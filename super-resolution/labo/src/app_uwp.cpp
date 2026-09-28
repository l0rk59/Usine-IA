// USR Labo -- version UWP : Xbox Series X|S en mode Developpeur (et PC).
//
// Application "CoreWindow" en C++/WinRT, sans XAML : une fenetre plein
// ecran, une chaine d'echange Direct3D 12 en 4K (Series X) ou 1440p
// (Series S), la manette via Windows.Gaming.Input. Tout le reste (menu,
// rendu, USR) est partage avec la version PC : labo_core, labo_renderer.
//
// Dans Dev Home, passer l'application en type "Game" : sinon elle n'a
// droit qu'a une fraction du GPU (voir docs/LABO.md).

#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <unknwn.h>  // avant C++/WinRT : active winrt::get_unknown
#include <windows.h>

#include <dxgi1_4.h>
#include <gamingdeviceinformation.h>

#include <winrt/Windows.ApplicationModel.h>
#include <winrt/Windows.ApplicationModel.Activation.h>
#include <winrt/Windows.ApplicationModel.Core.h>
#include <winrt/Windows.Foundation.h>
#include <winrt/Windows.Foundation.Collections.h>
#include <winrt/Windows.Gaming.Input.h>
#include <winrt/Windows.Graphics.Display.h>
#include <winrt/Windows.System.h>
#include <winrt/Windows.UI.Core.h>

#include <algorithm>
#include <chrono>
#include <cmath>
#include <string>

#include "labo_core.h"
#include "labo_frame.h"
#include "labo_renderer.h"

using namespace winrt;
using namespace winrt::Windows::ApplicationModel;
using namespace winrt::Windows::ApplicationModel::Activation;
using namespace winrt::Windows::ApplicationModel::Core;
using namespace winrt::Windows::Gaming::Input;
using namespace winrt::Windows::UI::Core;
using winrt::Windows::Foundation::IInspectable;

namespace {

constexpr uint32_t kFrames = 2;

// Taille recommandee par Microsoft pour une chaine d'echange UWP : 4K sur
// Series X, 1440p sur Series S. Renvoie false hors Xbox.
bool XboxDisplay(uint32_t* w, uint32_t* h, std::string* name)
{
    GAMING_DEVICE_MODEL_INFORMATION info = {};
    if (FAILED(GetGamingDeviceModelInformation(&info)) ||
        info.vendorId != GAMING_DEVICE_VENDOR_ID_MICROSOFT)
        return false;
    switch (info.deviceId) {
    case GAMING_DEVICE_DEVICE_ID_XBOX_ONE:
    case GAMING_DEVICE_DEVICE_ID_XBOX_ONE_S:
        *w = 1920; *h = 1080; *name = "Xbox One";
        break;
    case GAMING_DEVICE_DEVICE_ID_XBOX_SERIES_S:
        *w = 2560; *h = 1440; *name = "Xbox Series S";
        break;
    case GAMING_DEVICE_DEVICE_ID_XBOX_SERIES_X:
    case GAMING_DEVICE_DEVICE_ID_XBOX_SERIES_X_DEVKIT:
        *w = 3840; *h = 2160; *name = "Xbox Series X";
        break;
    default:  // One X, et consoles futures
        *w = 3840; *h = 2160; *name = "Xbox";
        break;
    }
    return true;
}

float Dead(double v)
{
    return (v > -0.2 && v < 0.2) ? 0.0f : static_cast<float>(v);
}

struct App : winrt::implements<App, IFrameworkViewSource, IFrameworkView> {
    IFrameworkView CreateView() { return *this; }

    void Initialize(CoreApplicationView const& view)
    {
        view.Activated({this, &App::OnActivated});
        CoreApplication::Suspending({this, &App::OnSuspending});
    }

    void Load(winrt::hstring const&) {}
    void Uninitialize() {}

    void SetWindow(CoreWindow const& window)
    {
        window.Closed({this, &App::OnClosed});
        window.KeyDown({this, &App::OnKeyDown});
        window.KeyUp({this, &App::OnKeyUp});
        // Sur Xbox, B declenche "Retour" : le Labo s'en sert pour son menu.
        SystemNavigationManager::GetForCurrentView().BackRequested(
            {this, &App::OnBackRequested});
    }

    void Run()
    {
        if (!InitGraphics()) {
            OutputDebugStringA(("USR Labo : " + error_ + "\n").c_str());
            return;
        }
        auto last = std::chrono::steady_clock::now();
        while (!exit_) {
            CoreWindow::GetForCurrentThread().Dispatcher().ProcessEvents(
                CoreProcessEventsOption::ProcessAllIfPresent);
            const auto now = std::chrono::steady_clock::now();
            const double dt = std::chrono::duration<double>(now - last).count();
            last = now;
            ctrl_.Update(ReadPad(), dt);
            uint32_t slot = 0;
            ID3D12GraphicsCommandList* cl = frames_.Begin(&slot);
            if (!renderer_.Record(cl, ctrl_, slot, dt))
                break;
            frames_.CopyToBackBuffer(
                renderer_.Output(),
                backBuffers_[swap_->GetCurrentBackBufferIndex()]);
            frames_.Submit();
            swap_->Present(1, 0);
        }
        Shutdown();
    }

private:
    bool Fail(const char* what)
    {
        error_ = what;
        return false;
    }

    bool InitGraphics()
    {
        if (FAILED(D3D12CreateDevice(nullptr, D3D_FEATURE_LEVEL_11_0,
                                     IID_PPV_ARGS(&device_))))
            return Fail("aucun peripherique Direct3D 12");

        uint32_t w = 0, h = 0;
        std::string name;
        if (!XboxDisplay(&w, &h, &name)) {
            const CoreWindow window = CoreWindow::GetForCurrentThread();
            const float dpi = winrt::Windows::Graphics::Display::
                DisplayInformation::GetForCurrentView().LogicalDpi();
            w = static_cast<uint32_t>(std::lround(window.Bounds().Width * dpi /
                                                  96.0f));
            h = static_cast<uint32_t>(std::lround(window.Bounds().Height * dpi /
                                                  96.0f));
            w = std::max(w, 640u);
            h = std::max(h, 360u);
            name = "PC (UWP)";
        }

        if (!frames_.Init(device_, kFrames, &error_))
            return false;
        labo::RendererDesc rd;
        rd.device = device_;
        rd.queue = frames_.queue();
        rd.displayWidth = w;
        rd.displayHeight = h;
        rd.framesInFlight = kFrames;
        rd.deviceName = name;
        rd.waitForGpu = [this]() { frames_.WaitIdle(); };
        if (!renderer_.Init(rd, &error_))
            return false;

        IDXGIFactory4* factory = nullptr;
        if (FAILED(CreateDXGIFactory2(0, IID_PPV_ARGS(&factory))))
            return Fail("fabrique DXGI");
        DXGI_SWAP_CHAIN_DESC1 sd = {};
        sd.Width = w;
        sd.Height = h;
        sd.Format = DXGI_FORMAT_R8G8B8A8_UNORM;
        sd.SampleDesc.Count = 1;
        sd.BufferUsage = DXGI_USAGE_RENDER_TARGET_OUTPUT;
        sd.BufferCount = kFrames;
        sd.SwapEffect = DXGI_SWAP_EFFECT_FLIP_DISCARD;
        sd.Scaling = DXGI_SCALING_ASPECT_RATIO_STRETCH;
        sd.AlphaMode = DXGI_ALPHA_MODE_IGNORE;
        IDXGISwapChain1* sc1 = nullptr;
        const HRESULT hr = factory->CreateSwapChainForCoreWindow(
            frames_.queue(), winrt::get_unknown(CoreWindow::GetForCurrentThread()),
            &sd, nullptr, &sc1);
        factory->Release();
        if (FAILED(hr) || FAILED(sc1->QueryInterface(IID_PPV_ARGS(&swap_)))) {
            if (sc1)
                sc1->Release();
            return Fail("chaine d'echange");
        }
        sc1->Release();
        for (uint32_t i = 0; i < kFrames; ++i)
            if (FAILED(swap_->GetBuffer(i, IID_PPV_ARGS(&backBuffers_[i]))))
                return Fail("tampons de la chaine d'echange");
        return true;
    }

    void Shutdown()
    {
        if (frames_.queue())
            frames_.WaitIdle();
        renderer_.Shutdown();
        for (auto& b : backBuffers_)
            if (b) {
                b->Release();
                b = nullptr;
            }
        if (swap_) {
            swap_->Release();
            swap_ = nullptr;
        }
        frames_.Shutdown();
        if (device_) {
            device_->Release();
            device_ = nullptr;
        }
    }

    labo::PadState ReadPad()
    {
        using winrt::Windows::System::VirtualKey;
        auto key = [this](VirtualKey k) {
            return keys_[static_cast<uint32_t>(k) & 0xFF];
        };
        labo::PadState p;
        const bool shift = key(VirtualKey::Shift);
        p.up = key(VirtualKey::Up);
        p.down = key(VirtualKey::Down);
        p.left = key(VirtualKey::Left);
        p.right = key(VirtualKey::Right);
        p.a = key(VirtualKey::Enter) || key(VirtualKey::Space);
        p.b = key(VirtualKey::Escape) || key(VirtualKey::Back);
        p.x = key(VirtualKey::X);
        p.y = key(VirtualKey::Y);
        p.lb = (key(VirtualKey::Tab) && shift) || key(VirtualKey::PageUp);
        p.rb = (key(VirtualKey::Tab) && !shift) || key(VirtualKey::PageDown);
        p.menu = key(VirtualKey::F1);
        p.view = key(VirtualKey::F2);
        p.rstick = key(VirtualKey::Z);
        p.lt = key(VirtualKey::Q) ? 1.0f : 0.0f;
        p.rt = key(VirtualKey::E) ? 1.0f : 0.0f;

        const auto pads = Gamepad::Gamepads();
        if (pads.Size() > 0) {
            const GamepadReading r = pads.GetAt(0).GetCurrentReading();
            auto has = [&r](GamepadButtons b) {
                return (r.Buttons & b) == b;
            };
            p.up |= has(GamepadButtons::DPadUp);
            p.down |= has(GamepadButtons::DPadDown);
            p.left |= has(GamepadButtons::DPadLeft);
            p.right |= has(GamepadButtons::DPadRight);
            p.a |= has(GamepadButtons::A);
            p.b |= has(GamepadButtons::B);
            p.x |= has(GamepadButtons::X);
            p.y |= has(GamepadButtons::Y);
            p.lb |= has(GamepadButtons::LeftShoulder);
            p.rb |= has(GamepadButtons::RightShoulder);
            p.menu |= has(GamepadButtons::Menu);
            p.view |= has(GamepadButtons::View);
            p.rstick |= has(GamepadButtons::RightThumbstick);
            p.lx = Dead(r.LeftThumbstickX);
            p.ly = Dead(r.LeftThumbstickY);
            p.rx = Dead(r.RightThumbstickX);
            p.ry = Dead(r.RightThumbstickY);
            p.lt = std::max(p.lt, static_cast<float>(r.LeftTrigger));
            p.rt = std::max(p.rt, static_cast<float>(r.RightTrigger));
        }
        return p;
    }

    void OnActivated(CoreApplicationView const&, IActivatedEventArgs const&)
    {
        CoreWindow::GetForCurrentThread().Activate();
    }

    void OnSuspending(IInspectable const&, SuspendingEventArgs const& args)
    {
        // Mise en veille (bouton Xbox, autre application) : le GPU doit
        // avoir fini avant que le systeme ne fige le processus.
        auto deferral = args.SuspendingOperation().GetDeferral();
        if (frames_.queue())
            frames_.WaitIdle();
        deferral.Complete();
    }

    void OnClosed(CoreWindow const&, CoreWindowEventArgs const&)
    {
        exit_ = true;
    }

    void OnKeyDown(CoreWindow const&, KeyEventArgs const& args)
    {
        keys_[static_cast<uint32_t>(args.VirtualKey()) & 0xFF] = true;
    }

    void OnKeyUp(CoreWindow const&, KeyEventArgs const& args)
    {
        keys_[static_cast<uint32_t>(args.VirtualKey()) & 0xFF] = false;
    }

    void OnBackRequested(IInspectable const&, BackRequestedEventArgs const& args)
    {
        args.Handled(true);
    }

    bool exit_ = false;
    bool keys_[256] = {};
    std::string error_;
    ID3D12Device* device_ = nullptr;
    IDXGISwapChain3* swap_ = nullptr;
    ID3D12Resource* backBuffers_[kFrames] = {};
    labo::FrameLoop frames_;
    labo::Renderer renderer_;
    labo::Controller ctrl_;
};

} // namespace

int __stdcall wWinMain(HINSTANCE, HINSTANCE, PWSTR, int)
{
    winrt::init_apartment();
    CoreApplication::Run(winrt::make<App>());
    return 0;
}
