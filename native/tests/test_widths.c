#include "compost/compost.h"

#include <stdint.h>
#include <stdio.h>

_Static_assert(sizeof(uint8_t) == 1U, "uint8_t must be one byte");
_Static_assert(sizeof(uint32_t) == 4U, "uint32_t must be four bytes");
_Static_assert(sizeof(uint64_t) == 8U, "uint64_t must be eight bytes");
_Static_assert(UINT64_MAX > UINT32_MAX, "uint64_t must be wider than uint32_t");
_Static_assert(COMPOST_MAX_ATOMS <= UINT32_MAX, "atom bound must fit uint32_t");
_Static_assert(COMPOST_MAX_RELATIONS <= UINT32_MAX, "relation bound must fit uint32_t");
_Static_assert(COMPOST_MAX_COMPOSITES <= UINT32_MAX, "composite bound must fit uint32_t");

int main(void)
{
    if (sizeof(size_t) < sizeof(uint32_t) || sizeof(double) != 8U) {
        (void)fprintf(stderr, "native width contract failed\n");
        return 1;
    }
    return 0;
}
