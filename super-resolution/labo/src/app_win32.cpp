// USR Labo -- version PC (Win32).
//
//   usr_labo                       fenetre 1280x720, clavier ou manette
//   usr_labo --largeur 1920 --hauteur 1080
//   usr_labo --capture 12 --dossier captures   sans fenetre : rend 12
//       images, ecrit captures/frame_NNN.bin (entrees et sortie de USR,
//       et de USR Universel si une vue l'affiche, pour la comparaison avec
//       la reference Python) et capture.png.
//   usr_labo --gauche 0 --droite 2   vues de depart (numeros : 0 USR + IA,
//       1 USR sans IA, 2 USR Universel, 3 bilineaire, 4 verite, 5 entree
//       brute, 6..9 diagnostics USR, 10 mouvement, 11..13 diagnostics
//       universels : reactivite, memoire, doute du flot).
//
// Clavier : fleches (croix), Entree (A), Echap (B), X, Y, Tab / Maj+Tab
// (RB / LB), F1 (menu), F2 (mesures), Q / E (gachettes), I J K L (stick
// droit), Z (loupe).

#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>

#include <d3d12sdklayers.h>
#include <dxgi1_4.h>
#include <xinput.h>

#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

#include "labo_core.h"
#include "labo_frame.h"
#include "labo_png.h"
#include "labo_renderer.h"

namespace {

struct Options {
    uint32_t width = 1280;
    uint32_t height = 720;
    int capture = 0;              // > 0 : mode sans fenetre
    std::string folder = "captures";
    int preset = -1;
    int page = 0;
    bool hideMenu = false;
    bool pause = false;
    int left = -1, right = -1;    // vues forcees (numero de labo::View)
    int zoom = -1;                // loupe forcee (0, 2, 4, 8)
    float zoomX = -1, zoomY = -1;  // position de la loupe (0..1)
    std::string name;             // nom affiche du GPU (captures)
    bool debugLayer = false;
};

bool ParseOptions(int argc, char** argv, Options* o)
{
    for (int i = 1; i < argc; ++i) {
        const std::string a = argv[i];
        const bool hasValue = i + 1 < argc;
        auto next = [&]() { return std::string(argv[++i]); };
        if (a == "--largeur" && hasValue) o->width = std::atoi(next().c_str());
        else if (a == "--hauteur" && hasValue) o->height = std::atoi(next().c_str());
        else if (a == "--capture" && hasValue) o->capture = std::atoi(next().c_str());
        else if (a == "--dossier" && hasValue) o->folder = next();
        else if (a == "--prereglage" && hasValue) o->preset = std::atoi(next().c_str());
        else if (a == "--page" && hasValue) o->page = std::atoi(next().c_str());
        else if (a == "--gauche" && hasValue) o->left = std::atoi(next().c_str());
        else if (a == "--droite" && hasValue) o->right = std::atoi(next().c_str());
        else if (a == "--loupe" && hasValue) o->zoom = std::atoi(next().c_str());
        else if (a == "--loupe-pos" && i + 2 < argc) {
            o->zoomX = static_cast<float>(std::atof(next().c_str()));
            o->zoomY = static_cast<float>(std::atof(next().c_str()));
        }
        else if (a == "--nom" && hasValue) o->name = next();
        else if (a == "--sans-menu") o->hideMenu = true;
        else if (a == "--pause") o->pause = true;
        else if (a == "--debug") o->debugLayer = true;
        else {
            std::fprintf(stderr, "option inconnue : %s\n", a.c_str());
            return false;
        }
    }
    const int views = static_cast<int>(labo::View::Count);
    return o->width >= 64 && o->height >= 64 && o->left < views &&
           o->right < views;
}

void Report(const Options& o, const std::string& message)
{
    std::fprintf(stderr, "USR Labo : %s\n", message.c_str());
    if (o.capture == 0)
        MessageBoxA(nullptr, message.c_str(), "USR Labo", MB_ICONERROR);
}

std::string Narrow(const wchar_t* w)
{
    const int n = WideCharToMultiByte(CP_UTF8, 0, w, -1, nullptr, 0, nullptr,
                                      nullptr);
    std::string s(n > 0 ? n - 1 : 0, '\0');
    if (n > 1)
        WideCharToMultiByte(CP_UTF8, 0, w, -1, &s[0], n, nullptr, nullptr);
    return s;
}

// --- entrees ----------------------------------------------------------------

bool g_keys[256] = {};
bool g_quit = false;

LRESULT CALLBACK WndProc(HWND hwnd, UINT msg, WPARAM wp, LPARAM lp)
{
    switch (msg) {
    case WM_KEYDOWN:
    case WM_SYSKEYDOWN:
        g_keys[wp & 0xFF] = true;
        return 0;
    case WM_KEYUP:
    case WM_SYSKEYUP:
        g_keys[wp & 0xFF] = false;
        return 0;
    case WM_KILLFOCUS:
        std::memset(g_keys, 0, sizeof(g_keys));
        return 0;
    case WM_CLOSE:
        g_quit = true;
        DestroyWindow(hwnd);
        return 0;
    case WM_DESTROY:
        PostQuitMessage(0);
        return 0;
    default:
        return DefWindowProcW(hwnd, msg, wp, lp);
    }
}

float Axis(SHORT v)
{
    const float f = static_cast<float>(v) / 32767.0f;
    return (f > -0.2f && f < 0.2f) ? 0.0f : (f < -1.0f ? -1.0f : f);
}

labo::PadState ReadPad()
{
    labo::PadState p;
    const bool shift = g_keys[VK_SHIFT];
    p.up = g_keys[VK_UP];
    p.down = g_keys[VK_DOWN];
    p.left = g_keys[VK_LEFT];
    p.right = g_keys[VK_RIGHT];
    p.a = g_keys[VK_RETURN] || g_keys[VK_SPACE];
    p.b = g_keys[VK_ESCAPE] || g_keys[VK_BACK];
    p.x = g_keys['X'];
    p.y = g_keys['Y'];
    p.lb = (g_keys[VK_TAB] && shift) || g_keys[VK_PRIOR];
    p.rb = (g_keys[VK_TAB] && !shift) || g_keys[VK_NEXT];
    p.menu = g_keys[VK_F1];
    p.view = g_keys[VK_F2];
    p.rstick = g_keys['Z'];
    p.lt = g_keys['Q'] ? 1.0f : 0.0f;
    p.rt = g_keys['E'] ? 1.0f : 0.0f;
    p.rx = (g_keys['L'] ? 1.0f : 0.0f) - (g_keys['J'] ? 1.0f : 0.0f);
    p.ry = (g_keys['I'] ? 1.0f : 0.0f) - (g_keys['K'] ? 1.0f : 0.0f);

    XINPUT_STATE xs = {};
    if (XInputGetState(0, &xs) == ERROR_SUCCESS) {
        const WORD b = xs.Gamepad.wButtons;
        p.up |= (b & XINPUT_GAMEPAD_DPAD_UP) != 0;
        p.down |= (b & XINPUT_GAMEPAD_DPAD_DOWN) != 0;
        p.left |= (b & XINPUT_GAMEPAD_DPAD_LEFT) != 0;
        p.right |= (b & XINPUT_GAMEPAD_DPAD_RIGHT) != 0;
        p.a |= (b & XINPUT_GAMEPAD_A) != 0;
        p.b |= (b & XINPUT_GAMEPAD_B) != 0;
        p.x |= (b & XINPUT_GAMEPAD_X) != 0;
        p.y |= (b & XINPUT_GAMEPAD_Y) != 0;
        p.lb |= (b & XINPUT_GAMEPAD_LEFT_SHOULDER) != 0;
        p.rb |= (b & XINPUT_GAMEPAD_RIGHT_SHOULDER) != 0;
        p.menu |= (b & XINPUT_GAMEPAD_START) != 0;
        p.view |= (b & XINPUT_GAMEPAD_BACK) != 0;
        p.rstick |= (b & XINPUT_GAMEPAD_RIGHT_THUMB) != 0;
        p.lx = Axis(xs.Gamepad.sThumbLX);
        p.ly = Axis(xs.Gamepad.sThumbLY);
        if (p.rx == 0.0f) p.rx = Axis(xs.Gamepad.sThumbRX);
        if (p.ry == 0.0f) p.ry = Axis(xs.Gamepad.sThumbRY);
        p.lt = std::max(p.lt, xs.Gamepad.bLeftTrigger / 255.0f);
        p.rt = std::max(p.rt, xs.Gamepad.bRightTrigger / 255.0f);
    }
    return p;
}

// --- capture --------------------------------------------------------------

bool WriteFrame(const std::string& path, const labo::Capture& c)
{
    FILE* f = std::fopen(path.c_str(), "wb");
    if (!f)
        return false;
    // En-tete de 32 octets, puis les tableaux bruts (petit-boutiste).
    char magic[8] = {'U', 'S', 'R', 'C', 'A', 'P', '1', 0};
    const uint32_t dims[4] = {c.displayW, c.displayH, c.renderW, c.renderH};
    bool ok = std::fwrite(magic, 1, 8, f) == 8 &&
              std::fwrite(dims, 4, 4, f) == 4 &&
              std::fwrite(c.jitter, 4, 2, f) == 2;
    auto put = [&](const void* data, size_t bytes) {
        ok = ok && std::fwrite(data, 1, bytes, f) == bytes;
    };
    put(c.composed.data(), c.composed.size());
    put(c.usrIA.data(), c.usrIA.size() * 2);
    put(c.sceneColor.data(), c.sceneColor.size() * 2);
    put(c.sceneDepth.data(), c.sceneDepth.size() * 4);
    put(c.sceneMotion.data(), c.sceneMotion.size() * 2);
    if (c.universal) {
        // Bloc optionnel : USR Universel (entree 8 bits et sortie).
        const char tag[4] = {'U', 'N', 'I', 'V'};
        const uint32_t info[2] = {c.universalPeriod, c.universalReset ? 1u : 0u};
        put(tag, 4);
        put(info, 8);
        put(c.universalJitter, 8);
        put(c.universalInput.data(), c.universalInput.size());
        put(c.universalOutput.data(), c.universalOutput.size() * 2);
    }
    return std::fclose(f) == 0 && ok;
}

// --- programme ------------------------------------------------------------

template <typename T>
void SafeRelease(T*& p)
{
    if (p) {
        p->Release();
        p = nullptr;
    }
}

int Run(const Options& o)
{
    if (o.debugLayer) {
        ID3D12Debug* dbg = nullptr;
        if (SUCCEEDED(D3D12GetDebugInterface(IID_PPV_ARGS(&dbg)))) {
            dbg->EnableDebugLayer();
            dbg->Release();
        }
    }
    ID3D12Device* device = nullptr;
    if (FAILED(D3D12CreateDevice(nullptr, D3D_FEATURE_LEVEL_11_0,
                                 IID_PPV_ARGS(&device)))) {
        Report(o, "aucun GPU Direct3D 12 disponible");
        return 1;
    }
    D3D12_FEATURE_DATA_SHADER_MODEL sm = {D3D_SHADER_MODEL_6_0};
    if (FAILED(device->CheckFeatureSupport(D3D12_FEATURE_SHADER_MODEL, &sm,
                                           sizeof(sm))) ||
        sm.HighestShaderModel < D3D_SHADER_MODEL_6_0) {
        Report(o, "le GPU ou son pilote ne gere pas le Shader Model 6.0");
        device->Release();
        return 1;
    }

    std::string deviceName = "PC";
    IDXGIFactory4* factory = nullptr;
    if (SUCCEEDED(CreateDXGIFactory2(0, IID_PPV_ARGS(&factory)))) {
        IDXGIAdapter1* adapter = nullptr;
        if (SUCCEEDED(factory->EnumAdapterByLuid(device->GetAdapterLuid(),
                                                 IID_PPV_ARGS(&adapter)))) {
            DXGI_ADAPTER_DESC1 ad = {};
            if (SUCCEEDED(adapter->GetDesc1(&ad)))
                deviceName = Narrow(ad.Description);
            adapter->Release();
        }
    }
    if (!o.name.empty())
        deviceName = o.name;
    if (deviceName.size() > 22)
        deviceName.resize(22);

    labo::FrameLoop frames;
    std::string error;
    const uint32_t kFrames = 2;
    if (!frames.Init(device, kFrames, &error)) {
        Report(o, error);
        return 1;
    }
    labo::Renderer renderer;
    labo::RendererDesc rd;
    rd.device = device;
    rd.queue = frames.queue();
    rd.displayWidth = o.width;
    rd.displayHeight = o.height;
    rd.framesInFlight = kFrames;
    rd.deviceName = deviceName;
    rd.waitForGpu = [&frames]() { frames.WaitIdle(); };
    if (!renderer.Init(rd, &error)) {
        Report(o, "initialisation du rendu : " + error);
        return 1;
    }

    labo::Controller ctrl;
    labo::Settings& s = ctrl.settings();
    if (o.preset >= 0)
        ctrl.ApplyPreset(static_cast<uint32_t>(o.preset));
    if (o.left >= 0) s.left = static_cast<labo::View>(o.left);
    if (o.right >= 0) s.right = static_cast<labo::View>(o.right);
    if (o.zoom >= 0) s.zoom = static_cast<uint32_t>(o.zoom);
    if (o.zoomX >= 0) s.zoomX = o.zoomX;
    if (o.zoomY >= 0) s.zoomY = o.zoomY;
    if (o.hideMenu) s.showMenu = false;
    if (o.pause) s.paused = true;
    for (int i = 0; i < o.page; ++i) {  // simule RB
        labo::PadState p;
        p.rb = true;
        ctrl.Update(p, 0.0);
        ctrl.Update(labo::PadState{}, 0.0);
    }

    int status = 0;
    if (o.capture > 0) {
        CreateDirectoryA(o.folder.c_str(), nullptr);
        labo::Capture cap;
        for (int f = 0; f < o.capture && status == 0; ++f) {
            ctrl.Update(labo::PadState{}, 1.0 / 60.0);
            uint32_t slot = 0;
            ID3D12GraphicsCommandList* cl = frames.Begin(&slot);
            if (!renderer.Record(cl, ctrl, slot, 1.0 / 60.0)) {
                Report(o, "echec de l'enregistrement de l'image");
                status = 1;
                break;
            }
            renderer.RecordCapture(cl);
            frames.Submit();
            frames.WaitIdle();
            char name[64];
            std::snprintf(name, sizeof(name), "/frame_%03d.bin", f);
            if (!renderer.ReadCapture(&cap) ||
                !WriteFrame(o.folder + name, cap)) {
                Report(o, "echec de la capture");
                status = 1;
            }
        }
        if (status == 0 &&
            !labo::WritePng(o.folder + "/capture.png", cap.composed,
                            cap.displayW, cap.displayH))
            status = 1;
        std::printf("%d image(s) capturee(s) dans %s (%s)\n", o.capture,
                    o.folder.c_str(), deviceName.c_str());
    } else {
        HINSTANCE inst = GetModuleHandleW(nullptr);
        WNDCLASSEXW wc = {};
        wc.cbSize = sizeof(wc);
        wc.lpfnWndProc = WndProc;
        wc.hInstance = inst;
        wc.hCursor = LoadCursor(nullptr, IDC_ARROW);
        wc.lpszClassName = L"USRLabo";
        RegisterClassExW(&wc);
        RECT r = {0, 0, static_cast<LONG>(o.width), static_cast<LONG>(o.height)};
        AdjustWindowRect(&r, WS_OVERLAPPEDWINDOW, FALSE);
        HWND hwnd = CreateWindowExW(0, wc.lpszClassName,
                                    L"USR Labo — super-résolution par IA",
                                    WS_OVERLAPPEDWINDOW, CW_USEDEFAULT,
                                    CW_USEDEFAULT, r.right - r.left,
                                    r.bottom - r.top, nullptr, nullptr, inst,
                                    nullptr);
        IDXGISwapChain1* sc1 = nullptr;
        IDXGISwapChain3* swap = nullptr;
        DXGI_SWAP_CHAIN_DESC1 sd = {};
        sd.Width = o.width;
        sd.Height = o.height;
        sd.Format = DXGI_FORMAT_R8G8B8A8_UNORM;
        sd.SampleDesc.Count = 1;
        sd.BufferUsage = DXGI_USAGE_RENDER_TARGET_OUTPUT;
        sd.BufferCount = kFrames;
        sd.SwapEffect = DXGI_SWAP_EFFECT_FLIP_DISCARD;
        sd.Scaling = DXGI_SCALING_STRETCH;
        if (!hwnd || !factory ||
            FAILED(factory->CreateSwapChainForHwnd(frames.queue(), hwnd, &sd,
                                                   nullptr, nullptr, &sc1)) ||
            FAILED(sc1->QueryInterface(IID_PPV_ARGS(&swap)))) {
            Report(o, "creation de la fenetre ou de la chaine d'echange");
            status = 1;
        }
        std::vector<ID3D12Resource*> backBuffers(kFrames, nullptr);
        for (uint32_t i = 0; status == 0 && i < kFrames; ++i)
            if (FAILED(swap->GetBuffer(i, IID_PPV_ARGS(&backBuffers[i]))))
                status = 1;
        if (status == 0)
            ShowWindow(hwnd, SW_SHOWDEFAULT);

        auto last = std::chrono::steady_clock::now();
        while (status == 0 && !g_quit) {
            MSG msg;
            while (PeekMessageW(&msg, nullptr, 0, 0, PM_REMOVE)) {
                if (msg.message == WM_QUIT)
                    g_quit = true;
                TranslateMessage(&msg);
                DispatchMessageW(&msg);
            }
            if (g_quit)
                break;
            const auto now = std::chrono::steady_clock::now();
            const double dt = std::chrono::duration<double>(now - last).count();
            last = now;
            ctrl.Update(ReadPad(), dt);
            uint32_t slot = 0;
            ID3D12GraphicsCommandList* cl = frames.Begin(&slot);
            if (!renderer.Record(cl, ctrl, slot, dt)) {
                Report(o, "echec de l'enregistrement de l'image");
                status = 1;
                break;
            }
            frames.CopyToBackBuffer(renderer.Output(),
                                    backBuffers[swap->GetCurrentBackBufferIndex()]);
            frames.Submit();
            swap->Present(1, 0);
        }
        frames.WaitIdle();
        for (auto*& b : backBuffers)
            SafeRelease(b);
        SafeRelease(swap);
        SafeRelease(sc1);
    }

    frames.WaitIdle();
    renderer.Shutdown();
    frames.Shutdown();
    SafeRelease(factory);
    device->Release();
    return status;
}

} // namespace

int main(int argc, char** argv)
{
    Options o;
    if (!ParseOptions(argc, argv, &o)) {
        std::fprintf(stderr,
                     "usage : usr_labo [--largeur L --hauteur H] "
                     "[--capture N --dossier D] [--prereglage I] [--page P] "
                     "[--gauche V --droite V] [--loupe Z] "
                     "[--loupe-pos X Y] [--nom TEXTE] [--sans-menu] "
                     "[--pause] "
                     "[--debug]\n");
        return 2;
    }
    return Run(o);
}
