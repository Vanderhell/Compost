#include "compost/compost.h"

#include <stdio.h>
#include <time.h>

int main(void)
{
    compost_config_t config = {0};
    compost_organism_t organism = {0};
    const uint8_t food[] = {1U, 2U, 1U, 2U};
    const double nutrition[] = {1.0, 1.0, 1.0, 1.0};
    const compost_step_input_t input = {food, nutrition, sizeof(food)};
    compost_step_result_t result = {0};
    const uint64_t iterations = UINT64_C(100000);
    if (compost_config_default(&config) != COMPOST_STATUS_OK ||
        compost_organism_init(&organism, &config, NULL, 1U) != COMPOST_STATUS_OK) {
        return 1;
    }
    const clock_t started = clock();
    for (uint64_t index = 0U; index < iterations; ++index) {
        if (compost_organism_digest(&organism, &input, &result) != COMPOST_STATUS_OK) {
            compost_organism_destroy(&organism);
            return 1;
        }
    }
    const clock_t elapsed = clock() - started;
    const double seconds = (double)elapsed / (double)CLOCKS_PER_SEC;
    (void)printf("backend=direct-c iterations=%llu bytes=%llu seconds=%.9f steps_per_second=%.3f\n",
        (unsigned long long)iterations,
        (unsigned long long)(iterations * (uint64_t)input.length),
        seconds,
        seconds > 0.0 ? (double)iterations / seconds : 0.0);
    compost_organism_destroy(&organism);
    return 0;
}
