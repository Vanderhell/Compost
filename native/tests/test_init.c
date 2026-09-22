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
    compost_status_t status = compost_config_default(&config);
    if (status != COMPOST_STATUS_OK) {
        return fail("default config");
    }
    status = compost_organism_init(&organism, &config, NULL, UINT64_C(42));
    if (status != COMPOST_STATUS_OK || !organism.initialized) {
        return fail("organism init");
    }
    if (organism.organism_id != UINT64_C(42) || organism.status != COMPOST_LIFECYCLE_ALIVE) {
        return fail("initial state");
    }
    if (compost_organism_init(&organism, &config, NULL, UINT64_C(43)) != COMPOST_STATUS_INVALID_STATE) {
        return fail("double init rejection");
    }
    compost_organism_destroy(&organism);
    if (organism.initialized) {
        return fail("destroy state");
    }
    return 0;
}
