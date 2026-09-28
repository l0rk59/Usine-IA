# USR -- Usine Super Resolution : bibliotheque statique Direct3D 12.
#
#   PC (Windows, SDK Windows 10/11) :
#     cmake -B build -G "Visual Studio 17 2022" -A x64
#     cmake --build build --config Release
#
#   Xbox Series X|S (Microsoft GDK, acces ID@Xbox requis) :
#     utilisez la toolchain CMake du GDK (plateforme Gaming.Xbox.Scarlett.x64)
#     et pointez USR_DXC vers le dxc du GDK, avec ses options console
#     dans USR_DXC_FLAGS. Voir docs/XBOX-SERIES-X.md.
#
#   Mode developpeur Xbox (UWP) : la bibliotheque s'utilise telle quelle
#   dans une application UWP DirectX 12 (bytecode DXIL standard).

cmake_minimum_required(VERSION 3.20)
project(usr VERSION 0.1.0 LANGUAGES CXX)

option(USR_NETWORK_HALF "Activations du reseau en min16float (FP16 compacte)" OFF)
set(USR_SHADER_MODEL "6_0" CACHE STRING "Shader model des passes compute")
set(USR_DXC_FLAGS "" CACHE STRING "Options supplementaires passees a dxc")

find_program(USR_DXC dxc
    HINTS "$ENV{WindowsSdkVerBinPath}/x64" "$ENV{GameDK}/bin"
    DOC "Compilateur de shaders dxc (celui du GDK pour la console)")
if(NOT USR_DXC)
    message(FATAL_ERROR "dxc introuvable : definir USR_DXC=/chemin/vers/dxc")
endif()

set(USR_SHADER_DIR "${CMAKE_CURRENT_SOURCE_DIR}/shaders")
set(USR_GEN_DIR "${CMAKE_CURRENT_BINARY_DIR}/generated")
file(MAKE_DIRECTORY "${USR_GEN_DIR}")

set(USR_SHADER_DEFINES "")
if(USR_NETWORK_HALF)
    list(APPEND USR_SHADER_DEFINES -DUSR_NETWORK_HALF=1)
endif()
separate_arguments(USR_DXC_EXTRA NATIVE_COMMAND "${USR_DXC_FLAGS}")

set(USR_SHADER_HEADERS "")
set(USR_SHADERS_INCLUDE "// Genere par CMake -- ne pas editer.\n#pragma once\n")
foreach(pass usr_prepare usr_accumulate usr_sharpen)
    set(out "${USR_GEN_DIR}/${pass}.h")
    add_custom_command(
        OUTPUT "${out}"
        COMMAND "${USR_DXC}" -T cs_${USR_SHADER_MODEL} -E main -O3 -WX
                ${USR_SHADER_DEFINES} ${USR_DXC_EXTRA}
                -Fh "${out}" -Vn g_${pass}
                "${USR_SHADER_DIR}/${pass}.hlsl"
        DEPENDS "${USR_SHADER_DIR}/${pass}.hlsl"
                "${USR_SHADER_DIR}/usr_common.hlsli"
                "${USR_SHADER_DIR}/usr_network.hlsli"
        COMMENT "dxc ${pass}.hlsl"
        VERBATIM)
    list(APPEND USR_SHADER_HEADERS "${out}")
    string(APPEND USR_SHADERS_INCLUDE "#include \"${pass}.h\"\n")
endforeach()
file(WRITE "${USR_GEN_DIR}/usr_shaders.h" "${USR_SHADERS_INCLUDE}")

add_library(usr STATIC
    src/usr_dx12.cpp
    src/usr_default_weights.h
    include/usr/usr.h
    ${USR_SHADER_HEADERS})
target_compile_features(usr PUBLIC cxx_std_17)
target_include_directories(usr
    PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/include"
    PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/src" "${USR_GEN_DIR}")
if(WIN32)
    target_link_libraries(usr PUBLIC d3d12)
endif()
