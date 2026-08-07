cmake_minimum_required(VERSION 3.22)

# ============================================================================
# Host-native unit tests for the portable layers (src/dsp, src/types).
#
# This is a SEPARATE CMake project from the firmware: it uses the system
# compiler, not arm-none-eabi-gcc.  One build tree can only ever have one
# compiler, which is why this cannot live in the root CMakeLists.txt.
#
#   cmake -S test -B build/test -G Ninja
#   cmake --build build/test
#   ctest --test-dir build/test --output-on-failure
#
# The Makefile wraps this as `make test`.
#
# Anything under src/dsp/ that fails to compile here has picked up a HAL
# dependency and broken the layering -- that is the point of this build.
# ============================================================================

project(patronus_tests C)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE "Debug")
endif()

option(TEST_SANITIZE "Build tests with AddressSanitizer + UBSan" ON)

enable_testing()

set(REPO_ROOT ${CMAKE_CURRENT_SOURCE_DIR}/..)

# ----------------------------------------------------------------------------
# Code under test: the same sources the firmware compiles, built natively.
# ----------------------------------------------------------------------------
file(GLOB_RECURSE DSP_SRC CONFIGURE_DEPENDS ${REPO_ROOT}/src/dsp/*.c)

if(NOT DSP_SRC)
    message(WARNING "No sources in src/dsp/ yet -- nothing to test")
    add_library(dsp INTERFACE)
    target_include_directories(dsp INTERFACE
        ${REPO_ROOT}/src/dsp ${REPO_ROOT}/src/types)
else()
    add_library(dsp STATIC ${DSP_SRC})
    target_include_directories(dsp PUBLIC
        ${REPO_ROOT}/src/dsp ${REPO_ROOT}/src/types)
    target_compile_options(dsp PRIVATE -Wall -Wextra -g -O1)
endif()

# ----------------------------------------------------------------------------
# Sanitizers.  Worth leaving on: most DSP bugs are off-by-one indexing into
# frame buffers, and ASan turns those from "wrong numbers somewhere downstream"
# into an exact file and line.
# ----------------------------------------------------------------------------
add_library(test_opts INTERFACE)
target_include_directories(test_opts INTERFACE ${CMAKE_CURRENT_SOURCE_DIR})
if(TEST_SANITIZE)
    target_compile_options(test_opts INTERFACE
        -fsanitize=address,undefined -fno-omit-frame-pointer -g)
    target_link_options(test_opts INTERFACE -fsanitize=address,undefined)
endif()

# ----------------------------------------------------------------------------
# One test_*.c == one executable == one ctest case.
# ----------------------------------------------------------------------------
file(GLOB TEST_SRC CONFIGURE_DEPENDS ${CMAKE_CURRENT_SOURCE_DIR}/test_*.c)

if(NOT TEST_SRC)
    message(STATUS "No test_*.c files in test/ yet")
endif()

foreach(TFILE ${TEST_SRC})
    get_filename_component(TNAME ${TFILE} NAME_WE)   # test_ringbuf

    add_executable(${TNAME} ${TFILE})
    target_link_libraries(${TNAME} PRIVATE dsp test_opts m)
    target_compile_options(${TNAME} PRIVATE -Wall -Wextra -g -O1)

    add_test(NAME ${TNAME} COMMAND ${TNAME})
    set_tests_properties(${TNAME} PROPERTIES TIMEOUT 30)
endforeach()

if(TEST_SRC)
    list(LENGTH TEST_SRC N_TESTS)
    message(STATUS "Host tests: ${N_TESTS} (sanitizers: ${TEST_SANITIZE})")
endif()
