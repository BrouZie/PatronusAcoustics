cmake_minimum_required(VERSION 3.22)

# ============================================================================
# Firmware build for NUCLEO-H723ZG (PatronusAcoustics)
#
# The ARM toolchain is deliberately NOT included from this file. Pass it on
# the command line so a stale cache can never silently fall back to /usr/bin/cc:
#
#   cmake -S . -B build/Debug -G Ninja \
#         --toolchain cmake/gcc-arm-none-eabi.cmake -DCMAKE_BUILD_TYPE=Debug
#
# The Makefile does this for you.  Host-side unit tests are a SEPARATE CMake
# project under test/ (native compiler, own build tree) -- see test/CMakeLists.txt.
# ============================================================================

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_C_EXTENSIONS ON)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE "Debug")
endif()

set(CMAKE_PROJECT_NAME NUCLEOH723ZG)
project(${CMAKE_PROJECT_NAME} C ASM)
message(STATUS "Build type: ${CMAKE_BUILD_TYPE}")

# Some arm-none-eabi builds report a bogus implicit link library named "ob".
list(REMOVE_ITEM CMAKE_C_IMPLICIT_LINK_LIBRARIES ob)

set(OPENOCD_INTERFACE "interface/stlink.cfg"  CACHE STRING "OpenOCD interface cfg")
set(OPENOCD_TARGET    "target/stm32h7x.cfg"   CACHE STRING "OpenOCD target cfg")

# ----------------------------------------------------------------------------
# CubeMX generated layer
#
# This CubeMX template attaches HAL sources, include dirs and startup code
# directly to a target named ${CMAKE_PROJECT_NAME} (rather than defining a
# self-contained INTERFACE library). So we create that target first and let
# the generated file fill it in.
#
# OBJECT, not STATIC: a static archive would let the linker discard
# startup_stm32h723xx.s, since nothing references the vector table by symbol.
# OBJECT libraries hand every .o to the linker directly.
# ----------------------------------------------------------------------------
add_library(${CMAKE_PROJECT_NAME} OBJECT)

add_subdirectory(cmake/stm32cubemx)

# Core/Src/main.c needs the app entry contract.
target_include_directories(${CMAKE_PROJECT_NAME} PRIVATE ${CMAKE_SOURCE_DIR}/src/apps)

# The generated file adds everything PRIVATE, so consumers see none of it.
# Promote include dirs and defines to INTERFACE so the apps inherit them.
get_target_property(_cube_inc ${CMAKE_PROJECT_NAME} INCLUDE_DIRECTORIES)
if(_cube_inc)
    target_include_directories(${CMAKE_PROJECT_NAME} INTERFACE ${_cube_inc})
endif()

get_target_property(_cube_def ${CMAKE_PROJECT_NAME} COMPILE_DEFINITIONS)
if(_cube_def)
    target_compile_definitions(${CMAKE_PROJECT_NAME} INTERFACE ${_cube_def})
endif()

# HAL usage requirements (headers + defines) WITHOUT the object files.
# This is what our hardware-facing static libraries consume.
add_library(hal_headers INTERFACE)
target_include_directories(hal_headers SYSTEM INTERFACE
    $<TARGET_PROPERTY:${CMAKE_PROJECT_NAME},INTERFACE_INCLUDE_DIRECTORIES>)
target_compile_definitions(hal_headers INTERFACE
    $<TARGET_PROPERTY:${CMAKE_PROJECT_NAME},INTERFACE_COMPILE_DEFINITIONS>)

# ----------------------------------------------------------------------------
# Shared vocabulary types -- headers only, no HAL, no code.
# ----------------------------------------------------------------------------
add_library(project_types INTERFACE)
target_include_directories(project_types INTERFACE ${CMAKE_SOURCE_DIR}/src/types)

# ----------------------------------------------------------------------------
# add_module(<name> <dir> [HAL])
#
# Creates a STATIC library from the .c files in <dir>, or a header-only
# INTERFACE library if there are none yet (so empty directories don't break
# the configure step while you're bootstrapping).
#
# Pass HAL to grant access to HAL/CMSIS headers.  Omitting it is what keeps
# src/dsp/ portable: a stray #include "stm32h7xx_hal.h" becomes a compile
# error rather than a code-review note.
# ----------------------------------------------------------------------------
function(add_module NAME DIR)
    cmake_parse_arguments(ARG "HAL" "" "" ${ARGN})

    set(SRC "")
    if(EXISTS ${DIR})
        file(GLOB_RECURSE SRC CONFIGURE_DEPENDS ${DIR}/*.c)
    endif()

    if(SRC)
        add_library(${NAME} STATIC ${SRC})
        set(SCOPE PUBLIC)
        target_compile_options(${NAME} PRIVATE -Wall -Wextra)
		if(ARG_HAL)
            target_link_libraries(${NAME} PRIVATE hal_headers)
            if(TARGET STM32_Drivers)
                target_link_libraries(${NAME} PUBLIC STM32_Drivers)
            endif()
        endif()
    else()
        add_library(${NAME} INTERFACE)
        set(SCOPE INTERFACE)
    endif()

    if(EXISTS ${DIR})
        target_include_directories(${NAME} ${SCOPE} ${DIR})
    endif()
    target_link_libraries(${NAME} ${SCOPE} project_types)
endfunction()

#                name        directory                          HAL access?
add_module(dsp        ${CMAKE_SOURCE_DIR}/src/dsp)            # portable, host-testable
add_module(drivers    ${CMAKE_SOURCE_DIR}/src/drivers   HAL)
add_module(config     ${CMAKE_SOURCE_DIR}/src/config    HAL)
add_module(time_sync  ${CMAKE_SOURCE_DIR}/src/time      HAL)
add_module(transport  ${CMAKE_SOURCE_DIR}/src/transport HAL)

set(APP_LIBS ${CMAKE_PROJECT_NAME} drivers dsp config time_sync transport)

# ----------------------------------------------------------------------------
# Applications: one subdirectory of src/apps/ == one flashable binary.
#
# Each app supplies main_app(); CubeMX's Core/Src/main.c provides main() and
# calls it, and arrives via the stm32cubemx interface library.
# ----------------------------------------------------------------------------
set(APPS "")
file(GLOB APP_CANDIDATES RELATIVE ${CMAKE_SOURCE_DIR}/src/apps
     ${CMAKE_SOURCE_DIR}/src/apps/*)

foreach(APP ${APP_CANDIDATES})
    set(APP_DIR ${CMAKE_SOURCE_DIR}/src/apps/${APP})
    if(NOT IS_DIRECTORY ${APP_DIR})
        continue()
    endif()

    file(GLOB_RECURSE APP_SRC CONFIGURE_DEPENDS ${APP_DIR}/*.c)
    if(NOT APP_SRC)
        message(WARNING "src/apps/${APP}/ has no .c files -- skipping")
        continue()
    endif()

    add_executable(${APP} ${APP_SRC})
	target_include_directories(${APP} PRIVATE ${APP_DIR} ${CMAKE_SOURCE_DIR}/src/apps)
    target_link_libraries(${APP} PRIVATE ${APP_LIBS})
    target_compile_options(${APP} PRIVATE -Wall -Wextra)

    # The toolchain file hardcodes -Wl,-Map=<project>.map, which would collide
    # across apps.  ld honours the last -Map on the command line.
    target_link_options(${APP} PRIVATE -Wl,-Map=${APP}.map)

    add_custom_command(TARGET ${APP} POST_BUILD
        COMMAND ${CMAKE_SIZE} $<TARGET_FILE:${APP}>
        COMMAND ${CMAKE_OBJCOPY} -O binary $<TARGET_FILE:${APP}> ${APP}.bin
        COMMENT "Size and .bin for ${APP}")

    add_custom_target(flash-${APP}
        COMMAND openocd -f ${OPENOCD_INTERFACE} -f ${OPENOCD_TARGET}
                -c "program $<TARGET_FILE:${APP}> verify reset exit"
        DEPENDS ${APP}
        USES_TERMINAL
        COMMENT "Flashing ${APP}")

    list(APPEND APPS ${APP})
endforeach()

if(APPS)
    add_custom_target(apps ALL DEPENDS ${APPS})
    message(STATUS "Applications: ${APPS}")
else()
    message(WARNING "No applications found under src/apps/")
endif()
