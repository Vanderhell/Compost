#include "compost/compost.h"

#include <stdio.h>

static int fail(const char *message, uint64_t step)
{
    (void)fprintf(stderr, "FAIL: %s at step %llu\n", message, (unsigned long long)step);
    return 1;
}

int main(void)
{
    compost_config_t config = {0};
    compost_organism_t first = {0};
    compost_organism_t second = {0};
    compost_cycle_result_t first_result = {0};
    compost_cycle_result_t second_result = {0};
    uint8_t food[16] = {0};
    double nutrition[16] = {0.0};
    if (compost_config_default(&config) != COMPOST_STATUS_OK ||
        compost_organism_init(&first, &config, NULL, UINT64_C(41)) != COMPOST_STATUS_OK ||
        compost_organism_init(&second, &config, NULL, UINT64_C(41)) != COMPOST_STATUS_OK) {
        return fail("setup", 0U);
    }
    uint64_t state = UINT64_C(0x9e3779b97f4a7c15);
    for (uint64_t step = 0U; step < UINT64_C(10000); ++step) {
        for (size_t index = 0U; index < sizeof(food); ++index) {
            state = state * UINT64_C(6364136223846793005) + UINT64_C(1442695040888963407);
            food[index] = (uint8_t)(state % UINT64_C(4));
            nutrition[index] = 1.0;
        }
        const compost_step_input_t input = {food, nutrition, sizeof(food)};
        const compost_status_t first_status = compost_organism_step(&first, &input, &first_result);
        const compost_status_t second_status = compost_organism_step(&second, &input, &second_result);
        if (first_status != COMPOST_STATUS_OK || second_status != COMPOST_STATUS_OK) {
            compost_organism_destroy(&first);
            compost_organism_destroy(&second);
            return fail("step", step);
        }
        if (compost_organism_state_digest(&first) != compost_organism_state_digest(&second) ||
            first_result.digestion.consumed_bytes != second_result.digestion.consumed_bytes ||
            first_result.digestion.assimilated_mass != second_result.digestion.assimilated_mass ||
            first_result.composites_consolidated != second_result.composites_consolidated) {
            compost_organism_destroy(&first);
            compost_organism_destroy(&second);
            return fail("deterministic replay", step);
        }
    }
    compost_organism_destroy(&first);
    compost_organism_destroy(&second);
    return 0;
}
