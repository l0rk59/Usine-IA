# USR -- Usine Super Resolution : bibliotheque Direct3D 12 + USR Labo.
#
#   PC (Windows, Visual Studio 2022, SDK Windows 10/11) :
#     cmake -B build -A x64
#     cmake --build build --config Release          -> usr.lib, usr_labo.exe
#
#   Xbox Series X|S en mode Developpeur (application UWP) :
#     cmake -B build-uwp -A x64 -DCMAKE_SYSTEM_NAME=WindowsStore ^
#           -DCMAKE_SYSTEM_VERSION=10.0.22621.0
#     puis ouvrir build-uwp/usr.sln, projet USRLabo, cible "Machine
#     distante" = l'adresse IP de la console. Voir docs/LABO.md.
#
#   Xbox via le GDK (studios ID@Xbox) : toolchain CMake du GDK, et USR_DXC
#   pointe vers le dxc du GDK. Voir docs/XBOX-SERIES-X.md.
#
#   Linux / macOS : seuls les tests du coeur du Labo (sans GPU) se
#   construisent : -DUSR_BUILD_LIBRARY=OFF -DUSR_BUILD_TESTS=ON.

cmake_minimum_required(VERSION 3.20)
project(usr VERSION 0.2.0 LANGUAGES CXX)

option(USR_BUILD_LIBRARY "Bibliotheque Direct3D 12 (usr)" ON)
option(USR_BUILD_LABO "Application USR Labo (PC ou UWP)" ${WIN32})
option(USR_BUILD_TESTS "Tests du coeur du Labo (sans GPU)" OFF)
option(USR_NETWORK_HALF "Activations du reseau en min16float (FP16 compacte)" OFF)
set(USR_SHADER_MODEL "6_0" CACHE STRING "Shader model des passes compute")
set(USR_DXC_FLAGS "" CACHE STRING "Options supplementaires passees a dxc")

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(USR_GEN_DIR "${CMAKE_CURRENT_BINARY_DIR}/generated")
file(MAKE_DIRECTORY "${USR_GEN_DIR}")

# Compile une liste de shaders compute en en-tetes C++ (tableaux g_<nom>)
# et ecrit un en-tete qui les inclut tous.
function(usr_compile_shaders out_var header shader_dir)
    set(outputs "")
    set(content "// Genere par CMake -- ne pas editer.\n#pragma once\n")
    file(GLOB includes "${shader_dir}/*.hlsli")
    foreach(pass ${ARGN})
        set(out "${USR_GEN_DIR}/${pass}.h")
        add_custom_command(
            OUTPUT "${out}"
            COMMAND "${USR_DXC}" -T cs_${USR_SHADER_MODEL} -E main -O3 -WX
                    ${USR_SHADER_DEFINES} ${USR_DXC_EXTRA}
                    -Fh "${out}" -Vn g_${pass} "${shader_dir}/${pass}.hlsl"
            DEPENDS "${shader_dir}/${pass}.hlsl" ${includes}
            COMMENT "dxc ${pass}.hlsl"
            VERBATIM)
        list(APPEND outputs "${out}")
        string(APPEND content "#include \"${pass}.h\"\n")
    endforeach()
    file(WRITE "${USR_GEN_DIR}/${header}" "${content}")
    set(${out_var} ${outputs} PARENT_SCOPE)
endfunction()

if(USR_BUILD_LIBRARY OR USR_BUILD_LABO)
    find_program(USR_DXC dxc
        HINTS "$ENV{WindowsSdkVerBinPath}/x64" "$ENV{GameDK}/bin"
        DOC "Compilateur de shaders dxc (celui du GDK pour la console)")
    if(NOT USR_DXC)
        message(FATAL_ERROR "dxc introuvable : definir USR_DXC=/chemin/vers/dxc")
    endif()
    set(USR_SHADER_DEFINES "")
    if(USR_NETWORK_HALF)
        list(APPEND USR_SHADER_DEFINES -DUSR_NETWORK_HALF=1)
    endif()
    separate_arguments(USR_DXC_EXTRA NATIVE_COMMAND "${USR_DXC_FLAGS}")
endif()

# --- Bibliotheque -------------------------------------------------------------
if(USR_BUILD_LIBRARY OR USR_BUILD_LABO)
    usr_compile_shaders(USR_SHADER_HEADERS usr_shaders.h
        "${CMAKE_CURRENT_SOURCE_DIR}/shaders"
        usr_prepare usr_accumulate usr_sharpen)
    # Mode Universel (sans vecteurs : emulateurs, captures)
    usr_compile_shaders(USR_U_SHADER_HEADERS usr_universal_shaders.h
        "${CMAKE_CURRENT_SOURCE_DIR}/shaders"
        usr_u_luma usr_u_down usr_u_grad usr_u_flow usr_u_median
        usr_u_finalize usr_u_residual usr_u_accumulate usr_u_output
        usr_u_interp_ecart usr_u_interp)
    add_library(usr STATIC
        src/usr_dx12.cpp
        src/usr_universal_dx12.cpp
        src/usr_d3d12_util.h
        src/usr_default_weights.h
        src/usr_universal_weights.h
        include/usr/usr.h
        ${USR_SHADER_HEADERS}
        ${USR_U_SHADER_HEADERS})
    target_compile_features(usr PUBLIC cxx_std_17)
    target_compile_definitions(usr PUBLIC NOMINMAX)
    target_include_directories(usr
        PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/include"
        PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/src" "${USR_GEN_DIR}")
    if(WIN32)
        target_link_libraries(usr PUBLIC d3d12)
    endif()
endif()

# --- USR Labo -----------------------------------------------------------------
set(LABO_DIR "${CMAKE_CURRENT_SOURCE_DIR}/labo")
set(LABO_CORE
    ${LABO_DIR}/src/labo_core.cpp
    ${LABO_DIR}/src/labo_core.h
    ${LABO_DIR}/src/labo_text.cpp
    ${LABO_DIR}/src/labo_text.h
    ${LABO_DIR}/src/labo_font.h
    ${LABO_DIR}/src/labo_scene_params.h)

if(USR_BUILD_LABO)
    usr_compile_shaders(LABO_SHADER_HEADERS labo_shaders.h
        "${LABO_DIR}/shaders"
        labo_scene labo_truth labo_upscale labo_compose labo_encode)
    set(LABO_SOURCES
        ${LABO_CORE}
        ${LABO_DIR}/src/labo_renderer.cpp
        ${LABO_DIR}/src/labo_renderer.h
        ${LABO_DIR}/src/labo_frame.cpp
        ${LABO_DIR}/src/labo_frame.h
        ${LABO_DIR}/src/labo_models.h
        ${LABO_SHADER_HEADERS})

    if(CMAKE_SYSTEM_NAME STREQUAL "WindowsStore")
        # Application UWP : Xbox Series X|S (mode Developpeur) et PC.
        set(LABO_ASSETS
            ${LABO_DIR}/uwp/Assets/Square44x44Logo.png
            ${LABO_DIR}/uwp/Assets/Square150x150Logo.png
            ${LABO_DIR}/uwp/Assets/Wide310x150Logo.png
            ${LABO_DIR}/uwp/Assets/StoreLogo.png
            ${LABO_DIR}/uwp/Assets/SplashScreen.png)
        add_executable(USRLabo WIN32
            ${LABO_SOURCES}
            ${LABO_DIR}/src/app_uwp.cpp
            ${LABO_DIR}/uwp/Package.appxmanifest
            ${LABO_ASSETS})
        set_property(SOURCE ${LABO_ASSETS} PROPERTY VS_DEPLOYMENT_CONTENT 1)
        set_property(SOURCE ${LABO_ASSETS} PROPERTY VS_DEPLOYMENT_LOCATION
                     "Assets")
        set_property(TARGET USRLabo PROPERTY
                     VS_WINDOWS_TARGET_PLATFORM_MIN_VERSION "10.0.19041.0")
        target_compile_definitions(USRLabo PRIVATE UNICODE _UNICODE)
        target_compile_options(USRLabo PRIVATE /EHsc /bigobj /utf-8)
        target_include_directories(USRLabo PRIVATE ${LABO_DIR}/src
                                   "${USR_GEN_DIR}")
        # C++/WinRT en C++17 passe par les coroutines experimentales (/await),
        # refusees par les compilateurs recents : C++20 et <coroutine>.
        set_property(TARGET USRLabo PROPERTY CXX_STANDARD 20)
        target_link_libraries(USRLabo PRIVATE usr d3d12 dxgi)
    elseif(WIN32)
        # Application PC (Win32) : fenetre, clavier / manette, --capture.
        add_executable(usr_labo
            ${LABO_SOURCES}
            ${LABO_DIR}/src/labo_png.cpp
            ${LABO_DIR}/src/labo_png.h
            ${LABO_DIR}/src/app_win32.cpp)
        target_compile_definitions(usr_labo PRIVATE UNICODE _UNICODE)
        if(MSVC)
            target_compile_options(usr_labo PRIVATE /utf-8)
        endif()
        target_include_directories(usr_labo PRIVATE ${LABO_DIR}/src
                                   "${USR_GEN_DIR}")
        target_link_libraries(usr_labo PRIVATE usr d3d12 dxgi xinput)
    endif()
endif()

# --- Tests du coeur du Labo (toutes plateformes, sans GPU) ---------------------
if(USR_BUILD_TESTS)
    enable_testing()
    add_executable(test_labo_core ${LABO_CORE}
        ${LABO_DIR}/tests/test_labo_core.cpp)
    target_include_directories(test_labo_core PRIVATE ${LABO_DIR}/src)
    if(MSVC)
        target_compile_options(test_labo_core PRIVATE /utf-8)
    endif()
    add_test(NAME labo_core COMMAND test_labo_core)
endif()
