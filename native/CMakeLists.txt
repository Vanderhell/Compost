cmake_minimum_required(VERSION 3.20)

project(compost_native VERSION 0.1.0 LANGUAGES C)

option(COMPOST_ENABLE_SANITIZERS "Enable AddressSanitizer and UndefinedBehaviorSanitizer" OFF)
option(COMPOST_BUILD_TESTS "Build native tests" ON)
option(COMPOST_BUILD_BENCHMARKS "Build native benchmarks" OFF)
option(COMPOST_WARNINGS_AS_ERRORS "Treat native compiler warnings as errors" OFF)

set(CMAKE_C_STANDARD 17)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_C_EXTENSIONS OFF)

if(COMPOST_WARNINGS_AS_ERRORS)
    if(CMAKE_C_COMPILER_ID MATCHES "GNU|Clang")
        add_compile_options(-Werror)
    elseif(MSVC)
        add_compile_options(/WX)
    endif()
endif()

add_library(compost_native SHARED
    src/compost.c
)
set_target_properties(compost_native PROPERTIES WINDOWS_EXPORT_ALL_SYMBOLS ON)

target_include_directories(compost_native
    PUBLIC
        ${CMAKE_CURRENT_SOURCE_DIR}/include
)

if(UNIX AND NOT APPLE)
    target_link_libraries(compost_native PRIVATE m)
endif()

if(CMAKE_C_COMPILER_ID MATCHES "GNU|Clang")
    target_compile_options(compost_native PRIVATE
        -Wall -Wextra -Wpedantic -Wconversion -Wsign-conversion -Wshadow
    )
endif()

if(COMPOST_ENABLE_SANITIZERS AND CMAKE_C_COMPILER_ID MATCHES "GNU|Clang")
    target_compile_options(compost_native PRIVATE -fsanitize=address,undefined -fno-omit-frame-pointer)
    target_link_options(compost_native PRIVATE -fsanitize=address,undefined)
elseif(COMPOST_ENABLE_SANITIZERS)
    message(WARNING "COMPOST_ENABLE_SANITIZERS requested, but this compiler is not configured for GCC/Clang sanitizer flags")
endif()

if(COMPOST_BUILD_TESTS)
    enable_testing()

    add_executable(compost_test_init tests/test_init.c)
    target_link_libraries(compost_test_init PRIVATE compost_native)

    add_executable(compost_test_snapshot tests/test_snapshot.c)
    target_link_libraries(compost_test_snapshot PRIVATE compost_native)

    add_executable(compost_test_abi tests/test_abi.c)
    target_link_libraries(compost_test_abi PRIVATE compost_native)

    add_executable(compost_test_robustness tests/test_robustness.c)
    target_link_libraries(compost_test_robustness PRIVATE compost_native)

    add_executable(compost_test_division tests/test_division.c)
    target_link_libraries(compost_test_division PRIVATE compost_native)

    add_executable(compost_test_replay tests/test_replay.c)
    target_link_libraries(compost_test_replay PRIVATE compost_native)

    add_executable(compost_test_fuzz tests/test_fuzz.c)
    target_link_libraries(compost_test_fuzz PRIVATE compost_native)

    add_executable(compost_test_widths tests/test_widths.c)
    target_link_libraries(compost_test_widths PRIVATE compost_native)

    if(CMAKE_C_COMPILER_ID MATCHES "GNU|Clang")
        target_compile_options(compost_test_init PRIVATE
            -Wall -Wextra -Wpedantic -Wconversion -Wsign-conversion -Wshadow
        )
        target_compile_options(compost_test_snapshot PRIVATE
            -Wall -Wextra -Wpedantic -Wconversion -Wsign-conversion -Wshadow
        )
        target_compile_options(compost_test_abi PRIVATE
            -Wall -Wextra -Wpedantic -Wconversion -Wsign-conversion -Wshadow
        )
        target_compile_options(compost_test_robustness PRIVATE
            -Wall -Wextra -Wpedantic -Wconversion -Wsign-conversion -Wshadow
        )
        target_compile_options(compost_test_division PRIVATE
            -Wall -Wextra -Wpedantic -Wconversion -Wsign-conversion -Wshadow
        )
        target_compile_options(compost_test_replay PRIVATE
            -Wall -Wextra -Wpedantic -Wconversion -Wsign-conversion -Wshadow
        )
        target_compile_options(compost_test_fuzz PRIVATE
            -Wall -Wextra -Wpedantic -Wconversion -Wsign-conversion -Wshadow
        )
        target_compile_options(compost_test_widths PRIVATE
            -Wall -Wextra -Wpedantic -Wconversion -Wsign-conversion -Wshadow
        )
    endif()

    if(COMPOST_ENABLE_SANITIZERS AND CMAKE_C_COMPILER_ID MATCHES "GNU|Clang")
        target_compile_options(compost_test_init PRIVATE -fsanitize=address,undefined -fno-omit-frame-pointer)
        target_link_options(compost_test_init PRIVATE -fsanitize=address,undefined)
        target_compile_options(compost_test_snapshot PRIVATE -fsanitize=address,undefined -fno-omit-frame-pointer)
        target_link_options(compost_test_snapshot PRIVATE -fsanitize=address,undefined)
        target_compile_options(compost_test_abi PRIVATE -fsanitize=address,undefined -fno-omit-frame-pointer)
        target_link_options(compost_test_abi PRIVATE -fsanitize=address,undefined)
        target_compile_options(compost_test_robustness PRIVATE -fsanitize=address,undefined -fno-omit-frame-pointer)
        target_link_options(compost_test_robustness PRIVATE -fsanitize=address,undefined)
        target_compile_options(compost_test_division PRIVATE -fsanitize=address,undefined -fno-omit-frame-pointer)
        target_link_options(compost_test_division PRIVATE -fsanitize=address,undefined)
        target_compile_options(compost_test_replay PRIVATE -fsanitize=address,undefined -fno-omit-frame-pointer)
        target_link_options(compost_test_replay PRIVATE -fsanitize=address,undefined)
        target_compile_options(compost_test_fuzz PRIVATE -fsanitize=address,undefined -fno-omit-frame-pointer)
        target_link_options(compost_test_fuzz PRIVATE -fsanitize=address,undefined)
        target_compile_options(compost_test_widths PRIVATE -fsanitize=address,undefined -fno-omit-frame-pointer)
        target_link_options(compost_test_widths PRIVATE -fsanitize=address,undefined)
    endif()

    add_test(NAME compost_init COMMAND compost_test_init)
    add_test(NAME compost_snapshot COMMAND compost_test_snapshot)
    add_test(NAME compost_abi COMMAND compost_test_abi)
    add_test(NAME compost_robustness COMMAND compost_test_robustness)
    add_test(NAME compost_division COMMAND compost_test_division)
    add_test(NAME compost_replay COMMAND compost_test_replay)
    add_test(NAME compost_fuzz COMMAND compost_test_fuzz)
    add_test(NAME compost_widths COMMAND compost_test_widths)
endif()

if(COMPOST_BUILD_BENCHMARKS)
    add_executable(compost_benchmark_digest bench/benchmark_digest.c)
    target_link_libraries(compost_benchmark_digest PRIVATE compost_native)
    if(CMAKE_C_COMPILER_ID MATCHES "GNU|Clang")
        target_compile_options(compost_benchmark_digest PRIVATE
            -Wall -Wextra -Wpedantic -Wconversion -Wsign-conversion -Wshadow
        )
    endif()
endif()
