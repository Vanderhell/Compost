#include "compost/compost.h"

#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int fail(const char *message)
{
    (void)fprintf(stderr, "FAIL: %s\n", message);
    return 1;
}

static void *always_fail_allocate(void *context, size_t size)
{
    (void)context;
    (void)size;
    return NULL;
}

static void always_fail_deallocate(void *context, void *memory)
{
    (void)context;
    (void)memory;
}

typedef struct allocator_probe {
    size_t allocations;
    size_t deallocations;
} allocator_probe_t;

static void *probe_allocate(void *context, size_t size)
{
    allocator_probe_t *probe = (allocator_probe_t *)context;
    void *memory = malloc(size);
    if (memory != NULL) {
        probe->allocations += 1U;
    }
    return memory;
}

static void probe_deallocate(void *context, void *memory)
{
    allocator_probe_t *probe = (allocator_probe_t *)context;
    if (memory != NULL) {
        probe->deallocations += 1U;
        free(memory);
    }
}

typedef struct allocation_limit {
    size_t allocations;
    size_t fail_after;
} allocation_limit_t;

static void *allocate_until_limit(void *context, size_t size)
{
    allocation_limit_t *limit = (allocation_limit_t *)context;
    if (limit->allocations >= limit->fail_after) return NULL;
    void *memory = malloc(size);
    if (memory != NULL) ++limit->allocations;
    return memory;
}

static void deallocate_until_limit(void *context, void *memory)
{
    (void)context;
    free(memory);
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
    if (strcmp(compost_status_name(COMPOST_STATUS_OK), "OK") != 0 ||
        strcmp(compost_status_name((compost_status_t)99), "UNKNOWN_STATUS") != 0 ||
        compost_config_default(NULL) != COMPOST_STATUS_INVALID_ARGUMENT ||
        compost_organism_init(NULL, &config, NULL, 0U) != COMPOST_STATUS_INVALID_ARGUMENT ||
        compost_organism_snapshot(NULL, &before) != COMPOST_STATUS_INVALID_ARGUMENT ||
        compost_organism_digest(NULL, &invalid, &result) != COMPOST_STATUS_INVALID_ARGUMENT ||
        compost_context_lifecycle_step(NULL, &invalid, NULL) != COMPOST_STATUS_INVALID_ARGUMENT) {
        return fail("null validation");
    }
    uint8_t territory_bit = UINT8_C(99);
    bool territory_contains = true;
    const uint8_t invalid_path[] = {UINT8_C(2)};
    if (compost_territory_address_bit(0U, COMPOST_MAX_TERRITORY_DEPTH, &territory_bit) != COMPOST_STATUS_INVALID_ARGUMENT ||
        territory_bit != UINT8_C(99) ||
        compost_territory_contains(invalid_path, 1U, 0U, &territory_contains) != COMPOST_STATUS_INVALID_ARGUMENT ||
        territory_contains != true ||
        compost_territory_contains(NULL, 1U, 0U, &territory_contains) != COMPOST_STATUS_INVALID_ARGUMENT) {
        return fail("territory invalid input");
    }
    const uint8_t block_file[] = "firmware-A";
    uint64_t block_key = 0U;
    if (compost_territory_food_block_key(
            block_file, sizeof(block_file) - 1U, UINT64_C(7), &block_key
        ) != COMPOST_STATUS_OK ||
        block_key != UINT64_C(4863105638158506395) ||
        compost_territory_food_block_key(NULL, 1U, 0U, &block_key) != COMPOST_STATUS_INVALID_ARGUMENT ||
        block_key != UINT64_C(4863105638158506395)) {
        return fail("food block key validation");
    }
    compost_context_t *try_child_sentinel = (compost_context_t *)(uintptr_t)1U;
    compost_division_plan_t try_plan_sentinel = {0};
    compost_division_result_t try_result_sentinel = {0};
    try_plan_sentinel.candidate_found = true;
    try_plan_sentinel.boundary_ratio = 7.0;
    try_result_sentinel.cross_split_mass = UINT64_C(9);
    if (compost_context_try_divide(
            NULL, 1U, &try_child_sentinel, &try_plan_sentinel, &try_result_sentinel
        ) != COMPOST_STATUS_INVALID_ARGUMENT ||
        try_child_sentinel != (compost_context_t *)(uintptr_t)1U ||
        !try_plan_sentinel.candidate_found || try_plan_sentinel.boundary_ratio != 7.0 ||
        try_result_sentinel.cross_split_mass != UINT64_C(9)) {
        return fail("try-division failed-output preservation");
    }
    if (compost_config_default(&config) != COMPOST_STATUS_OK) {
        return fail("default config");
    }
    compost_context_t *invalid_lifecycle_context = NULL;
    compost_cycle_result_t invalid_lifecycle_result = {0};
    invalid_lifecycle_result.digestion.consumed_bytes = SIZE_MAX;
    if (compost_create(&config, UINT64_C(3), &invalid_lifecycle_context) != COMPOST_STATUS_OK) {
        return fail("invalid lifecycle setup");
    }
    const uint64_t invalid_lifecycle_before =
        compost_context_state_digest(invalid_lifecycle_context);
    if (compost_context_lifecycle_step(
            invalid_lifecycle_context, &invalid, &invalid_lifecycle_result
        ) != COMPOST_STATUS_INVALID_ARGUMENT ||
        compost_context_state_digest(invalid_lifecycle_context) != invalid_lifecycle_before ||
        invalid_lifecycle_result.digestion.consumed_bytes != SIZE_MAX) {
        compost_destroy(invalid_lifecycle_context);
        return fail("invalid lifecycle rollback");
    }
    compost_destroy(invalid_lifecycle_context);

    compost_context_t *step_overflow_context = NULL;
    compost_snapshot_t step_overflow_snapshot = {0};
    compost_metabolic_snapshot_t step_overflow_metabolic = {0};
    compost_cycle_result_t step_overflow_result = {0};
    const compost_step_input_t step_overflow_input = {NULL, NULL, 0U};
    if (compost_create(&config, UINT64_C(31), &step_overflow_context) != COMPOST_STATUS_OK ||
        compost_context_snapshot(step_overflow_context, &step_overflow_snapshot) != COMPOST_STATUS_OK ||
        compost_context_metabolic_snapshot(step_overflow_context, &step_overflow_metabolic) != COMPOST_STATUS_OK) {
        compost_destroy(step_overflow_context);
        return fail("metabolic-step overflow setup");
    }
    step_overflow_metabolic.steps = UINT64_MAX;
    if (compost_context_restore_snapshot(
            step_overflow_context, &step_overflow_snapshot, &step_overflow_metabolic
        ) != COMPOST_STATUS_OK) {
        compost_destroy(step_overflow_context);
        return fail("metabolic-step overflow restore");
    }
    const uint64_t step_overflow_before = compost_context_state_digest(step_overflow_context);
    step_overflow_result.digestion.consumed_bytes = SIZE_MAX;
    if (compost_context_lifecycle_step(
            step_overflow_context, &step_overflow_input, &step_overflow_result
        ) != COMPOST_STATUS_INVALID_ARGUMENT ||
        compost_context_state_digest(step_overflow_context) != step_overflow_before ||
        step_overflow_result.digestion.consumed_bytes != SIZE_MAX ||
        compost_context_metabolic_snapshot(step_overflow_context, &step_overflow_metabolic) != COMPOST_STATUS_OK ||
        step_overflow_metabolic.steps != UINT64_MAX) {
        compost_destroy(step_overflow_context);
        return fail("metabolic-step overflow rollback");
    }
    compost_destroy(step_overflow_context);

    compost_allocator_t failing_allocator = {
        NULL, always_fail_allocate, always_fail_deallocate
    };
    compost_context_t *failed_context = NULL;
    if (compost_create_with_allocator(&config, &failing_allocator, 2U, &failed_context) != COMPOST_STATUS_OUT_OF_MEMORY ||
        failed_context != NULL) {
        return fail("allocation failure injection");
    }
    compost_allocator_t incomplete_allocator = {
        NULL, always_fail_allocate, NULL
    };
    compost_context_t *invalid_allocator_context = (compost_context_t *)(uintptr_t)1U;
    if (compost_create_with_allocator(
            &config, &incomplete_allocator, UINT64_C(2), &invalid_allocator_context
        ) != COMPOST_STATUS_INVALID_ARGUMENT ||
        invalid_allocator_context != (compost_context_t *)(uintptr_t)1U) {
        return fail("incomplete allocator rejection");
    }
    allocation_limit_t limited = {0U, 1U};
    compost_allocator_t limited_allocator = {
        &limited, allocate_until_limit, deallocate_until_limit
    };
    compost_config_t division_config = config;
    division_config.boundary_ratio_limit = 0.5;
    division_config.birth_reserve = 10.0;
    compost_context_t *failed_child_parent = NULL;
    compost_context_t *failed_child = (compost_context_t *)(uintptr_t)1U;
    compost_division_plan_t failed_child_plan = {0};
    compost_division_result_t failed_child_result = {0};
    const uint8_t division_food[] = {1U, 2U};
    const double division_nutrition[] = {1.0, 1.0};
    const compost_step_input_t division_input = {
        division_food, division_nutrition, sizeof(division_food)
    };
    compost_step_result_t division_digest = {0};
    if (compost_create_with_allocator(
            &division_config, &limited_allocator, 8U, &failed_child_parent
        ) != COMPOST_STATUS_OK ||
        compost_context_digest(failed_child_parent, &division_input, &division_digest) != COMPOST_STATUS_OK) {
        compost_destroy(failed_child_parent);
        return fail("failed-child parent setup");
    }
    const uint64_t failed_child_parent_before = compost_context_state_digest(failed_child_parent);
    if (compost_context_try_divide(
            failed_child_parent, 9U, &failed_child, &failed_child_plan, &failed_child_result
        ) != COMPOST_STATUS_OUT_OF_MEMORY ||
        failed_child != NULL ||
        compost_context_state_digest(failed_child_parent) != failed_child_parent_before) {
        compost_destroy(failed_child);
        compost_destroy(failed_child_parent);
        return fail("failed-child allocation rollback");
    }
    compost_destroy(failed_child_parent);

    allocation_limit_t local_limited = {0U, 1U};
    compost_allocator_t local_limited_allocator = {
        &local_limited, allocate_until_limit, deallocate_until_limit
    };
    compost_config_t local_config = division_config;
    local_config.reproduction_minimum_body = UINT64_C(2);
    compost_context_t *failed_local_parent = NULL;
    compost_context_t *failed_local_child = (compost_context_t *)(uintptr_t)1U;
    compost_division_result_t failed_local_result = {0};
    failed_local_result.cross_split_mass = UINT64_C(95);
    const uint8_t local_food[] = {1U, 2U, 3U, 4U};
    const double local_nutrition[] = {2.0, 2.0, 2.0, 2.0};
    const compost_step_input_t local_input = {
        local_food, local_nutrition, sizeof(local_food)
    };
    compost_step_result_t local_digest = {0};
    if (compost_create_with_allocator(
            &local_config, &local_limited_allocator, UINT64_C(10), &failed_local_parent
        ) != COMPOST_STATUS_OK ||
        compost_context_digest(failed_local_parent, &local_input, &local_digest) != COMPOST_STATUS_OK) {
        compost_destroy(failed_local_parent);
        return fail("failed-local parent setup");
    }
    const uint64_t failed_local_before = compost_context_state_digest(failed_local_parent);
    if (compost_context_try_local_reproduction(
            failed_local_parent, UINT64_C(11), &failed_local_child, &failed_local_result
        ) != COMPOST_STATUS_OUT_OF_MEMORY ||
        failed_local_child != NULL ||
        failed_local_result.cross_split_mass != 0U ||
        compost_context_state_digest(failed_local_parent) != failed_local_before) {
        compost_destroy(failed_local_child);
        compost_destroy(failed_local_parent);
        return fail("failed-local allocation rollback");
    }
    compost_destroy(failed_local_parent);
    allocator_probe_t probe = {0U, 0U};
    compost_allocator_t probe_allocator = {
        &probe, probe_allocate, probe_deallocate
    };
    compost_context_t *probed_context = NULL;
    compost_snapshot_t probed_snapshot = {0};
    if (compost_create_with_allocator(&config, &probe_allocator, 5U, &probed_context) != COMPOST_STATUS_OK ||
        probed_context == NULL ||
        compost_context_snapshot(probed_context, &probed_snapshot) != COMPOST_STATUS_OK ||
        probed_snapshot.organism_id != UINT64_C(5) ||
        probe.allocations != 1U) {
        compost_destroy(probed_context);
        return fail("custom allocator creation");
    }
    compost_destroy(probed_context);
    if (probe.deallocations != 1U) {
        return fail("custom allocator destruction");
    }
    compost_context_t *partition_parent = NULL;
    compost_context_t *partition_child = NULL;
    compost_division_result_t partition_result = {0};
    if (compost_create_with_allocator(&config, &probe_allocator, 6U, &partition_parent) != COMPOST_STATUS_OK ||
        partition_parent == NULL ||
        compost_context_partition(
            partition_parent, 7U, NULL, 0U, 1.0, &partition_child, &partition_result
        ) != COMPOST_STATUS_INVALID_ARGUMENT ||
        partition_child != NULL || probe.allocations != 3U || probe.deallocations != 2U) {
        compost_destroy(partition_child);
        compost_destroy(partition_parent);
        return fail("custom allocator failed partition cleanup");
    }
    compost_destroy(partition_parent);
    if (probe.deallocations != 3U) {
        return fail("custom allocator partition lifetime");
    }
    config.abi_version = UINT32_C(1);
    if (compost_organism_init(&organism, &config, NULL, 3U) != COMPOST_STATUS_INVALID_ARGUMENT) {
        return fail("ABI mismatch rejection");
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

    compost_config_t extreme_config = {0};
    compost_organism_t extreme = {0};
    compost_snapshot_t extreme_snapshot = {0};
    compost_step_input_t empty_input = {NULL, NULL, 0U};
    compost_cycle_result_t extreme_result = {0};
    if (compost_config_default(&extreme_config) != COMPOST_STATUS_OK) {
        return fail("extreme config setup");
    }
    extreme_config.max_body_mass = UINT64_MAX;
    extreme_config.reproduction_minimum_body = UINT64_MAX;
    if (compost_organism_init(&extreme, &extreme_config, NULL, UINT64_MAX) != COMPOST_STATUS_OK ||
        extreme.organism_id != UINT64_MAX) {
        compost_organism_destroy(&extreme);
        return fail("integer extrema initialization");
    }
    extreme.age_in_cycles = UINT64_MAX;
    const uint64_t extreme_before = compost_organism_state_digest(&extreme);
    if (compost_organism_step(&extreme, &empty_input, &extreme_result) != COMPOST_STATUS_INVALID_ARGUMENT ||
        compost_organism_snapshot(&extreme, &extreme_snapshot) != COMPOST_STATUS_OK ||
        extreme_snapshot.organism_id != UINT64_MAX ||
        extreme_snapshot.age_in_cycles != UINT64_MAX ||
        compost_organism_state_digest(&extreme) != extreme_before) {
        compost_organism_destroy(&extreme);
        return fail("integer extrema rejection");
    }
    compost_organism_destroy(&extreme);
    compost_organism_destroy(&organism);
    if (compost_organism_snapshot(&organism, &after) != COMPOST_STATUS_INVALID_STATE) {
        return fail("destroyed state");
    }
    if (compost_organism_init(&organism, &config, NULL, 4U) != COMPOST_STATUS_OK) {
        return fail("corrupt state setup");
    }
    organism.status = (compost_lifecycle_status_t)99;
    (void)memset(&after, 0xA5, sizeof(after));
    compost_snapshot_t invalid_status_sentinel = after;
    if (compost_organism_snapshot(&organism, &after) != COMPOST_STATUS_INVALID_STATE ||
        memcmp(&after, &invalid_status_sentinel, sizeof(after)) != 0) {
        compost_organism_destroy(&organism);
        return fail("invalid lifecycle enum output preservation");
    }
    compost_organism_destroy(&organism);
    if (compost_organism_init(&organism, &config, NULL, 5U) != COMPOST_STATUS_OK) {
        return fail("invalid gut setup");
    }
    organism.gut[0].mass = 2U;
    organism.gut[0].payload_length = 1U;
    if (compost_organism_snapshot(&organism, &after) != COMPOST_STATUS_INVALID_STATE) {
        compost_organism_destroy(&organism);
        return fail("invalid gut rejection");
    }
    compost_gut_process_result_t gut_result = {7U, 8U, 9U, 10U};
    if (compost_organism_process_gut(&organism, 1U, &gut_result) != COMPOST_STATUS_INVALID_STATE ||
        gut_result.processed_mass != 7U || gut_result.assimilated_mass != 8U ||
        gut_result.rejected_mass != 9U || gut_result.expelled_mass != 10U ||
        compost_organism_enqueue_resorbed(&organism, 1U) != COMPOST_STATUS_INVALID_STATE) {
        compost_organism_destroy(&organism);
        return fail("invalid gut operation rejection");
    }
    compost_organism_destroy(&organism);
    if (compost_organism_init(&organism, &config, NULL, 6U) != COMPOST_STATUS_OK) {
        return fail("external enqueue setup");
    }
    compost_snapshot_t enqueue_before = {0};
    compost_snapshot_t enqueue_after = {0};
    if (compost_organism_snapshot(&organism, &enqueue_before) != COMPOST_STATUS_OK ||
        compost_organism_enqueue_external(&organism, &invalid) != COMPOST_STATUS_INVALID_ARGUMENT ||
        compost_organism_snapshot(&organism, &enqueue_after) != COMPOST_STATUS_OK ||
        memcmp(&enqueue_before, &enqueue_after, sizeof(enqueue_before)) != 0) {
        compost_organism_destroy(&organism);
        return fail("external enqueue transactional failure");
    }
    compost_organism_destroy(&organism);
    return 0;
}
