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
    if (compost_config_default(&config) != COMPOST_STATUS_OK) {
        return fail("default config");
    }
    compost_allocator_t failing_allocator = {
        NULL, always_fail_allocate, always_fail_deallocate
    };
    compost_context_t *failed_context = NULL;
    if (compost_create_with_allocator(&config, &failing_allocator, 2U, &failed_context) != COMPOST_STATUS_OUT_OF_MEMORY ||
        failed_context != NULL) {
        return fail("allocation failure injection");
    }
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
    compost_organism_destroy(&organism);
    if (compost_organism_snapshot(&organism, &after) != COMPOST_STATUS_INVALID_STATE) {
        return fail("destroyed state");
    }
    if (compost_organism_init(&organism, &config, NULL, 4U) != COMPOST_STATUS_OK) {
        return fail("corrupt state setup");
    }
    organism.status = (compost_lifecycle_status_t)99;
    if (compost_organism_snapshot(&organism, &after) != COMPOST_STATUS_INVALID_STATE) {
        compost_organism_destroy(&organism);
        return fail("invalid lifecycle enum");
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
