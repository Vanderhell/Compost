#include "compost/compost.h"

#include <math.h>
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

static bool finite(double value)
{
    return isfinite(value) != 0;
}

static bool add_u64(uint64_t left, uint64_t right, uint64_t *result)
{
    if (UINT64_MAX - left < right) {
        return false;
    }
    *result = left + right;
    return true;
}

static bool valid_costs(const compost_activity_costs_t *costs)
{
    if (costs == NULL) {
        return false;
    }
    return finite(costs->byte) && finite(costs->digest_per_kib) &&
           finite(costs->reject_per_kib) && finite(costs->resorption_per_kib) &&
           finite(costs->relation_created) && finite(costs->relation_strengthened) &&
           finite(costs->composite_created) && finite(costs->composite_strengthened) &&
           finite(costs->structural_mass_delta) && finite(costs->resorption) &&
           finite(costs->division) && finite(costs->basal_mass) &&
           finite(costs->settlement_base) && finite(costs->settlement_mass_scale);
}

compost_status_t compost_structural_mass(double strength, uint64_t *mass)
{
    if (mass == NULL || !finite(strength)) {
        return COMPOST_STATUS_INVALID_ARGUMENT;
    }
    if (strength < 1.0) {
        *mass = UINT64_C(0);
        return COMPOST_STATUS_OK;
    }
    const double logarithm = floor(log2(strength));
    if (!finite(logarithm) || logarithm < 0.0 || logarithm > (double)(UINT64_MAX - 1U)) {
        return COMPOST_STATUS_INVALID_ARGUMENT;
    }
    *mass = UINT64_C(1) + (uint64_t)logarithm;
    return COMPOST_STATUS_OK;
}

compost_status_t compost_activity_ledger_add(
    compost_activity_ledger_t *ledger,
    const compost_activity_counters_t *counters,
    uint64_t body_mass,
    const compost_activity_costs_t *costs
)
{
    if (ledger == NULL || counters == NULL || !valid_costs(costs)) {
        return COMPOST_STATUS_INVALID_ARGUMENT;
    }
    (void)body_mass;
    compost_activity_ledger_t next = *ledger;
    const uint64_t *source = &counters->bytes_eaten;
    uint64_t *destination = &next.counters.bytes_eaten;
    const size_t count = sizeof(*counters) / sizeof(uint64_t);
    for (size_t index = 0U; index < count; ++index) {
        if (!add_u64(destination[index], source[index], &destination[index])) {
            return COMPOST_STATUS_INVALID_ARGUMENT;
        }
    }
    const double kib = 1024.0;
    const double delta =
        costs->byte * (double)counters->bytes_eaten +
        costs->digest_per_kib * ((double)counters->processed_bytes / kib) +
        costs->reject_per_kib * ((double)counters->rejected_bytes / kib) +
        costs->resorption_per_kib * ((double)counters->resorbed_processed_bytes / kib) +
        costs->relation_created * (double)counters->relations_created +
        costs->relation_strengthened * (double)counters->relations_strengthened +
        costs->composite_created * (double)counters->composites_created +
        costs->composite_strengthened * (double)counters->composites_strengthened +
        costs->structural_mass_delta * ((double)counters->structural_mass_added + (double)counters->structural_mass_lost) +
        costs->resorption * (double)counters->resorption_events +
        costs->division * (double)counters->division_events;
    if (!finite(delta) || !finite(next.metabolic_debt + delta)) {
        return COMPOST_STATUS_INVALID_ARGUMENT;
    }
    next.metabolic_debt += delta;
    *ledger = next;
    return COMPOST_STATUS_OK;
}

compost_status_t compost_activity_settlement_threshold(
    uint64_t body_mass,
    const compost_activity_costs_t *costs,
    double *threshold
)
{
    if (threshold == NULL || !valid_costs(costs)) {
        return COMPOST_STATUS_INVALID_ARGUMENT;
    }
    *threshold = costs->settlement_base + costs->settlement_mass_scale * (double)body_mass;
    return finite(*threshold) ? COMPOST_STATUS_OK : COMPOST_STATUS_INVALID_ARGUMENT;
}

compost_status_t compost_activity_basal_cost(
    uint64_t body_mass,
    const compost_activity_costs_t *costs,
    double *cost
)
{
    if (cost == NULL || !valid_costs(costs)) {
        return COMPOST_STATUS_INVALID_ARGUMENT;
    }
    *cost = costs->basal_mass * (double)body_mass;
    return finite(*cost) ? COMPOST_STATUS_OK : COMPOST_STATUS_INVALID_ARGUMENT;
}

compost_status_t compost_forgetting_delta(
    double strength,
    double income_rate,
    double maintenance,
    double income_decay,
    compost_forgetting_delta_t *delta
)
{
    if (delta == NULL || !finite(strength) || !finite(income_rate) ||
        !finite(maintenance) || !finite(income_decay) ||
        !(income_decay > 0.0 && income_decay < 1.0)) {
        return COMPOST_STATUS_INVALID_ARGUMENT;
    }
    double strength_after = strength;
    if (income_rate <= maintenance) {
        const double decayed = strength * income_decay;
        strength_after = decayed > 1.0 ? decayed : 1.0;
    }
    delta->strength_after = strength_after;
    delta->income_rate_after = income_rate * income_decay;
    return finite(delta->strength_after) && finite(delta->income_rate_after)
        ? COMPOST_STATUS_OK : COMPOST_STATUS_INVALID_ARGUMENT;
}

compost_status_t compost_maintenance_weakening_budget(
    double maintenance_deficit,
    uint64_t body_mass,
    uint64_t *budget
)
{
    if (budget == NULL || !finite(maintenance_deficit)) {
        return COMPOST_STATUS_INVALID_ARGUMENT;
    }
    if (maintenance_deficit <= 0.0) {
        *budget = UINT64_C(0);
        return COMPOST_STATUS_OK;
    }
    const uint64_t denominator = body_mass > 0U ? body_mass : UINT64_C(1);
    const double quotient = ceil(maintenance_deficit / (double)denominator);
    if (!finite(quotient) || quotient < 1.0 || quotient > (double)UINT64_MAX) {
        return COMPOST_STATUS_INVALID_ARGUMENT;
    }
    *budget = (uint64_t)quotient;
    return COMPOST_STATUS_OK;
}
