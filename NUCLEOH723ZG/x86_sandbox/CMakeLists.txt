cmake_minimum_required(VERSION 3.25)

# ============================================================================
# x86 sandbox: prototype DSP code on the host before moving it into src/dsp.
#
#   "make sandbox" or:
#   cmake -S x86_sandbox -B build/x86_sandbox \
#       && cmake --build build/x86_sandbox
# ============================================================================

project(x86_sandbox C)

set(CMAKE_EXPORT_COMPILE_COMMANDS ON)
set(CMAKE_BUILD_TYPE Debug)

set(CMSISDSP_INSTALL OFF CACHE BOOL "" FORCE)

# CMSIS-DSP built for the host: __GNUC_PYTHON__ drops the Cortex-M intrinsics
add_subdirectory(../CMSIS-DSP/Source bin_dsp)
target_compile_definitions(CMSISDSP PUBLIC __GNUC_PYTHON__)
set_target_properties(CMSISDSP PROPERTIES SYSTEM ON)   # no -Wconversion noise from CMSIS headers

add_executable(x86
    platform.c
    main.c
    dsp.c
)

target_link_libraries(x86 PRIVATE
    CMSISDSP
    m
)

target_compile_options(x86 PRIVATE
    -Wall
    -Wextra
    -Wconversion
    -Wsign-conversion
    -Wshadow
)
