#include "compost/compost.h"

#include <math.h>
#include <stdint.h>
#include <stdio.h>

static int fail(const char *message)
{
    (void)fprintf(stderr, "FAIL: %s\n", message);
    return 1;
}

static uint32_t next_value(uint32_t *state)
{
    *state = (*state * UINT32_C(1664525)) + UINT32_C(1013904223);
    return *state;
}

int main(void)
{
    compost_config_t config = {0};
    compost_organism_t first = {0};
    compost_organism_t second = {0};
    if (compost_config_default(&config) != COMPOST_STATUS_OK ||
        compost_organism_init(&first, &config, NULL, UINT64_C(41)) != COMPOST_STATUS_OK ||
        compost_organism_init(&second, &config, NULL, UINT64_C(41)) != COMPOST_STATUS_OK) {
        return fail("setup");
    }
    uint32_t random_state = UINT32_C(0xC0FFEE12);
    for (size_t iteration = 0U; iteration < 10000U; ++iteration) {
        uint8_t food[8] = {0};
        double nutrition[8] = {0.0};
        const size_t length = (size_t)(next_value(&random_state) % UINT32_C(9));
        for (size_t index = 0U; index < length; ++index) {
            food[index] = (uint8_t)(next_value(&random_state) % UINT32_C(8));
            nutrition[index] = (double)(next_value(&random_state) % UINT32_C(4));
        }
        if (iteration % 17U == 0U && length > 0U) nutrition[0] = NAN;
        compost_step_input_t input = {food, nutrition, length};
        compost_cycle_result_t first_result = {0};
        compost_cycle_result_t second_result = {0};
        const uint64_t first_before = compost_organism_state_digest(&first);
        const uint64_t second_before = compost_organism_state_digest(&second);
        const compost_status_t first_status = compost_organism_step(&first, &input, &first_result);
        const compost_status_t second_status = compost_organism_step(&second, &input, &second_result);
        if (first_status != second_status ||
            compost_organism_state_digest(&first) != compost_organism_state_digest(&second) ||
            (first_status != COMPOST_STATUS_OK &&
             (compost_organism_state_digest(&first) != first_before ||
              compost_organism_state_digest(&second) != second_before))) {
            compost_organism_destroy(&first);
            compost_organism_destroy(&second);
            return fail("deterministic transactional fuzz case");
        }
        if (iteration % 19U == 0U) {
            compost_step_input_t invalid = {NULL, NULL, 1U};
            const uint64_t before = compost_organism_state_digest(&first);
            if (compost_organism_step(&first, &invalid, &first_result) != COMPOST_STATUS_INVALID_ARGUMENT ||
                compost_organism_state_digest(&first) != before) {
                compost_organism_destroy(&first);
                compost_organism_destroy(&second);
                return fail("invalid input mutation");
            }
        }
    }
    compost_organism_destroy(&first);
    compost_organism_destroy(&second);
    return 0;
}
