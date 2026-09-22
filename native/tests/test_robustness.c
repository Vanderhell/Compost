#include "compost/compost.h"

#include <math.h>
#include <stdio.h>
#include <string.h>

static int fail(const char *message)
{
    (void)fprintf(stderr, "FAIL: %s\n", message);
    return 1;
}

int main(void)
{
    compost_config_t config = {0};
    compost_organism_t organism = {0};
    compost_snapshot_t before = {0};
    compost_snapshot_t after = {0};
    compost_step_result_t result = {0};
    const uint8_t food[] = {1U};
    const double nan_value = NAN;
    const compost_step_input_t invalid = {food, &nan_value, 1U};
    if (compost_config_default(NULL) != COMPOST_STATUS_INVALID_ARGUMENT ||
        compost_organism_init(NULL, &config, NULL, 0U) != COMPOST_STATUS_INVALID_ARGUMENT ||
        compost_organism_snapshot(NULL, &before) != COMPOST_STATUS_INVALID_ARGUMENT ||
        compost_organism_digest(NULL, &invalid, &result) != COMPOST_STATUS_INVALID_ARGUMENT) {
        return fail("null validation");
    }
    if (compost_config_default(&config) != COMPOST_STATUS_OK ||
        compost_organism_init(&organism, &config, NULL, 3U) != COMPOST_STATUS_OK ||
        compost_organism_snapshot(&organism, &before) != COMPOST_STATUS_OK ||
        compost_organism_digest(&organism, &invalid, &result) != COMPOST_STATUS_INVALID_ARGUMENT ||
        compost_organism_snapshot(&organism, &after) != COMPOST_STATUS_OK ||
        memcmp(&before, &after, sizeof(before)) != 0) {
        compost_organism_destroy(&organism);
        return fail("failed operation mutated state");
    }
    compost_organism_destroy(&organism);
    compost_organism_destroy(&organism);
    if (compost_organism_snapshot(&organism, &after) != COMPOST_STATUS_INVALID_STATE) {
        return fail("destroyed state");
    }
    return 0;
}
