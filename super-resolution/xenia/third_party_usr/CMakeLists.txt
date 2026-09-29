# USR -- Usine Super Resolution, integre a Xenia (mode Universel).
#
# Copie par xenia/appliquer.ps1 (ou .sh) du depot Usine-IA dans
# third_party/usr de Xenia, avec include/, src/ et shaders/ de USR.
# Bibliotheque statique compilee comme les autres dependances tierces de
# Xenia (sans /WX) ; ses shaders compute (Shader Model 6.0) sont compiles
# par dxc, celui du Windows SDK par defaut (il signe le DXIL avec dxil.dll).

set(USR_DXC "" CACHE FILEPATH "dxc.exe pour les shaders de USR (vide : Windows SDK)")
if(NOT USR_DXC)
  set(_usr_pf86 "ProgramFiles(x86)")
  file(GLOB _usr_dxc_candidates
    "$ENV{${_usr_pf86}}/Windows Kits/10/bin/*/x64/dxc.exe")
  if(_usr_dxc_candidates)
    # la version la plus recente du SDK en premier
    list(SORT _usr_dxc_candidates COMPARE NATURAL)
    list(REVERSE _usr_dxc_candidates)
    list(GET _usr_dxc_candidates 0 _usr_dxc_found)
    set(USR_DXC "${_usr_dxc_found}" CACHE FILEPATH "" FORCE)
  endif()
endif()
if(NOT USR_DXC)
  find_program(USR_DXC dxc)
endif()
if(NOT USR_DXC)
  message(FATAL_ERROR
    "USR : dxc introuvable. Installer le Windows SDK (10.0.19041 ou plus) "
    "ou definir -DUSR_DXC=C:/chemin/vers/dxc.exe")
endif()
message(STATUS "USR : shaders compiles par ${USR_DXC}")

set(_usr_gen "${CMAKE_CURRENT_BINARY_DIR}/generated")
file(MAKE_DIRECTORY "${_usr_gen}")
file(GLOB _usr_includes "${CMAKE_CURRENT_SOURCE_DIR}/shaders/*.hlsli")

function(usr_shader_header header)
  set(_outputs "")
  set(_content "// Genere par CMake -- ne pas editer.\n#pragma once\n")
  foreach(pass ${ARGN})
    set(_out "${_usr_gen}/${pass}.h")
    add_custom_command(
      OUTPUT "${_out}"
      COMMAND "${USR_DXC}" -T cs_6_0 -E main -O3 -WX
              -Fh "${_out}" -Vn g_${pass}
              "${CMAKE_CURRENT_SOURCE_DIR}/shaders/${pass}.hlsl"
      DEPENDS "${CMAKE_CURRENT_SOURCE_DIR}/shaders/${pass}.hlsl" ${_usr_includes}
      COMMENT "dxc ${pass}.hlsl"
      VERBATIM)
    list(APPEND _outputs "${_out}")
    string(APPEND _content "#include \"${pass}.h\"\n")
  endforeach()
  file(WRITE "${_usr_gen}/${header}" "${_content}")
  set(USR_SHADER_OUTPUTS ${USR_SHADER_OUTPUTS} ${_outputs} PARENT_SCOPE)
endfunction()

set(USR_SHADER_OUTPUTS "")
usr_shader_header(usr_shaders.h usr_prepare usr_accumulate usr_sharpen)
usr_shader_header(usr_universal_shaders.h
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
  ${USR_SHADER_OUTPUTS})
target_include_directories(usr
  PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/include"
  PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/src" "${_usr_gen}")
target_compile_definitions(usr PRIVATE NOMINMAX)
target_compile_features(usr PUBLIC cxx_std_17)
