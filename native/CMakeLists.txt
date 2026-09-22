cmake_minimum_required(VERSION 3.20)

project(compost_native VERSION 0.1.0 LANGUAGES C)

option(COMPOST_ENABLE_SANITIZERS "Enable AddressSanitizer and UndefinedBehaviorSanitizer" OFF)
option(COMPOST_BUILD_TESTS "Build native tests" ON)

set(CMAKE_C_STANDARD 17)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_C_EXTENSIONS OFF)

add_library(compost_native STATIC
    src/compost.c
)

target_include_directories(compost_native
    PUBLIC
        ${CMAKE_CURRENT_SOURCE_DIR}/include
)

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

    if(CMAKE_C_COMPILER_ID MATCHES "GNU|Clang")
        target_compile_options(compost_test_init PRIVATE
            -Wall -Wextra -Wpedantic -Wconversion -Wsign-conversion -Wshadow
        )
        target_compile_options(compost_test_snapshot PRIVATE
            -Wall -Wextra -Wpedantic -Wconversion -Wsign-conversion -Wshadow
        )
    endif()

    if(COMPOST_ENABLE_SANITIZERS AND CMAKE_C_COMPILER_ID MATCHES "GNU|Clang")
        target_compile_options(compost_test_init PRIVATE -fsanitize=address,undefined -fno-omit-frame-pointer)
        target_link_options(compost_test_init PRIVATE -fsanitize=address,undefined)
        target_compile_options(compost_test_snapshot PRIVATE -fsanitize=address,undefined -fno-omit-frame-pointer)
        target_link_options(compost_test_snapshot PRIVATE -fsanitize=address,undefined)
    endif()

    add_test(NAME compost_init COMMAND compost_test_init)
    add_test(NAME compost_snapshot COMMAND compost_test_snapshot)
endif()
