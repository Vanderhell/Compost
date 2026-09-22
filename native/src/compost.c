#include "compost/compost.h"

#include <stdlib.h>
#include <string.h>

static void *default_allocate(void *context, size_t size)
{
    (void)context;
    return malloc(size);
}

static void default_deallocate(void *context, void *memory)
{
    (void)context;
    free(memory);
}

static bool valid_allocator(const compost_allocator_t *allocator)
{
    return allocator == NULL ||
           (allocator->allocate != NULL && allocator->deallocate != NULL);
}

static compost_allocator_t effective_allocator(const compost_allocator_t *allocator)
{
    compost_allocator_t result = {0};
    if (allocator != NULL) {
        result = *allocator;
    }
    if (result.allocate == NULL && result.deallocate == NULL) {
        result.allocate = default_allocate;
        result.deallocate = default_deallocate;
    }
    return result;
}

static bool valid_config(const compost_config_t *config)
{
    return config != NULL &&
           config->abi_version == COMPOST_NATIVE_ABI_VERSION &&
           config->max_body_mass > 0U &&
           config->max_territory_depth <= COMPOST_MAX_TERRITORY_DEPTH &&
           config->income_decay > 0.0 && config->income_decay < 1.0;
}

compost_status_t compost_config_default(compost_config_t *config)
{
    if (config == NULL) {
        return COMPOST_STATUS_INVALID_ARGUMENT;
    }
    config->abi_version = COMPOST_NATIVE_ABI_VERSION;
    config->seed = UINT64_C(0);
    config->max_body_mass = UINT64_MAX;
    config->max_territory_depth = COMPOST_MAX_TERRITORY_DEPTH;
    config->income_decay = 0.8;
    return COMPOST_STATUS_OK;
}

compost_status_t compost_organism_init(
    compost_organism_t *organism,
    const compost_config_t *config,
    const compost_allocator_t *allocator,
    uint64_t organism_id
)
{
    if (organism == NULL || !valid_config(config) || !valid_allocator(allocator)) {
        return COMPOST_STATUS_INVALID_ARGUMENT;
    }
    if (organism->initialized) {
        return COMPOST_STATUS_INVALID_STATE;
    }

    memset(organism, 0, sizeof(*organism));
    organism->allocator = effective_allocator(allocator);
    organism->config = *config;
    organism->organism_id = organism_id;
    organism->status = COMPOST_LIFECYCLE_ALIVE;
    organism->territory.organism_id = organism_id;
    organism->territory.alive = true;
    organism->initialized = true;
    return COMPOST_STATUS_OK;
}

void compost_organism_destroy(compost_organism_t *organism)
{
    if (organism == NULL) {
        return;
    }
    memset(organism, 0, sizeof(*organism));
}

compost_status_t compost_organism_snapshot(
    const compost_organism_t *organism,
    compost_snapshot_t *snapshot
)
{
    if (organism == NULL || snapshot == NULL) {
        return COMPOST_STATUS_INVALID_ARGUMENT;
    }
    if (!organism->initialized) {
        return COMPOST_STATUS_INVALID_STATE;
    }
    memset(snapshot, 0, sizeof(*snapshot));
    snapshot->abi_version = COMPOST_NATIVE_ABI_VERSION;
    snapshot->organism_id = organism->organism_id;
    snapshot->parent_id = organism->parent_id;
    snapshot->has_parent = organism->has_parent;
    snapshot->generation = organism->generation;
    snapshot->cursor = organism->cursor;
    snapshot->age_in_cycles = organism->age_in_cycles;
    snapshot->status = organism->status;
    snapshot->reserve = organism->reserve;
    snapshot->body = organism->body;
    snapshot->material_flow = organism->material_flow;
    snapshot->activity = organism->activity;
    snapshot->territory = organism->territory;
    return COMPOST_STATUS_OK;
}

const char *compost_status_name(compost_status_t status)
{
    switch (status) {
    case COMPOST_STATUS_OK:
        return "OK";
    case COMPOST_STATUS_INVALID_ARGUMENT:
        return "INVALID_ARGUMENT";
    case COMPOST_STATUS_INVALID_STATE:
        return "INVALID_STATE";
    case COMPOST_STATUS_OUT_OF_MEMORY:
        return "OUT_OF_MEMORY";
    case COMPOST_STATUS_BUFFER_TOO_SMALL:
        return "BUFFER_TOO_SMALL";
    default:
        return "UNKNOWN_STATUS";
    }
}
