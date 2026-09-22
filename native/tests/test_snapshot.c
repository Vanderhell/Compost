#include "compost/compost.h"

#include <stdio.h>

static int fail(const char *message)
{
    (void)fprintf(stderr, "FAIL: %s\n", message);
    return 1;
}

int main(void)
{
    compost_config_t config = {0};
    compost_organism_t organism = {0};
    compost_snapshot_t snapshot = {0};
    if (compost_config_default(&config) != COMPOST_STATUS_OK ||
        compost_organism_init(&organism, &config, NULL, UINT64_C(7)) != COMPOST_STATUS_OK) {
        return fail("setup");
    }
    organism.generation = UINT64_C(3);
    organism.cursor = UINT64_C(11);
    organism.reserve = 2.5;
    organism.body.atom_count = UINT64_C(4);
    organism.body.structural_mass = UINT64_C(9);
    organism.territory.depth = 2U;
    organism.territory.path[0] = 1U;
    organism.territory.path[1] = 0U;
    if (compost_organism_snapshot(&organism, &snapshot) != COMPOST_STATUS_OK) {
        return fail("snapshot");
    }
    if (snapshot.organism_id != UINT64_C(7) || snapshot.generation != UINT64_C(3) ||
        snapshot.cursor != UINT64_C(11) || snapshot.reserve != 2.5 ||
        snapshot.body.atom_count != UINT64_C(4) || snapshot.body.structural_mass != UINT64_C(9) ||
        snapshot.territory.depth != 2U || snapshot.territory.path[0] != 1U ||
        snapshot.territory.path[1] != 0U) {
        return fail("snapshot values");
    }
    compost_organism_destroy(&organism);
    if (compost_organism_snapshot(&organism, &snapshot) != COMPOST_STATUS_INVALID_STATE) {
        return fail("destroyed snapshot rejection");
    }
    return 0;
}
