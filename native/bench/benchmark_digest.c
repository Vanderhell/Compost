#include "compost/compost.h"

#include <stdio.h>
#include <time.h>

int main(void)
{
    compost_config_t config = {0};
    const uint8_t food[] = {1U, 2U, 1U, 2U};
    const double nutrition[] = {1.0, 1.0, 1.0, 1.0};
    const compost_step_input_t input = {food, nutrition, sizeof(food)};
    compost_step_result_t result = {0};
    const uint64_t iterations = UINT64_C(100000);
    const size_t repetitions = 5U;
    double seconds[5] = {0.0};
    if (compost_config_default(&config) != COMPOST_STATUS_OK) {
        return 1;
    }
    for (size_t repetition = 0U; repetition < repetitions; ++repetition) {
        compost_organism_t organism = {0};
        if (compost_organism_init(&organism, &config, NULL, (uint64_t)repetition + UINT64_C(1)) != COMPOST_STATUS_OK) {
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
        seconds[repetition] = (double)elapsed / (double)CLOCKS_PER_SEC;
        compost_organism_destroy(&organism);
    }
    for (size_t left = 0U; left < repetitions; ++left) {
        for (size_t right = left + 1U; right < repetitions; ++right) {
            if (seconds[right] < seconds[left]) {
                const double swap = seconds[left];
                seconds[left] = seconds[right];
                seconds[right] = swap;
            }
        }
    }
    const double median = seconds[repetitions / 2U];
    (void)printf("backend=direct-c repetitions=%llu iterations=%llu bytes=%llu min_seconds=%.9f median_seconds=%.9f max_seconds=%.9f median_steps_per_second=%.3f\n",
        (unsigned long long)repetitions,
        (unsigned long long)iterations,
        (unsigned long long)(iterations * (uint64_t)input.length),
        seconds[0],
        median,
        seconds[repetitions - 1U],
        median > 0.0 ? (double)iterations / median : 0.0);
    return 0;
}
