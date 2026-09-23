#include "compost/compost.h"

#include <math.h>
#include <stdlib.h>
#include <string.h>

struct compost_context {
    compost_allocator_t allocator;
    compost_organism_t organism;
    uint64_t metabolic_progress;
    uint64_t metabolic_steps;
};

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

static bool finite(double value);
static bool add_double(double left, double right, double *result);
static uint64_t digest_u64(uint64_t digest, uint64_t value);
static compost_status_t activity_delta(
    const compost_activity_counters_t *counters,
    const compost_activity_costs_t *costs,
    double *delta
);
static compost_status_t activity_charge_only(
    compost_activity_ledger_t *ledger,
    const compost_activity_counters_t *counters,
    const compost_activity_costs_t *costs
);
static compost_status_t settle_activity_debt(compost_organism_t *organism);
static bool weaker(const compost_structure_t *left, const compost_structure_t *right);
static compost_structure_t *weakest_structure(compost_organism_t *organism);
static double structure_maintenance(const compost_organism_t *organism);
static compost_status_t label_components(
    const compost_organism_t *organism,
    bool skip_boundary,
    uint8_t boundary_left,
    uint8_t boundary_right,
    uint8_t labels[COMPOST_MAX_ATOMS],
    uint8_t *component_count
);
static compost_status_t remove_structure_entry(
    compost_organism_t *organism,
    compost_structure_t *structure,
    uint64_t *resorbed_mass
);
static compost_status_t remove_weakest_for_pressure(
    compost_organism_t *organism,
    uint64_t *resorbed_mass
);
static compost_status_t remove_weakest_for_capacity(
    compost_organism_t *organism,
    uint64_t *resorbed_mass
);
static compost_status_t lifecycle_maintenance(
    compost_organism_t *organism,
    compost_maintenance_result_t *result
);
static uint64_t structure_count(const compost_organism_t *organism);
static const compost_structure_t *atom_for_key(const compost_organism_t *organism, uint8_t key);

static const compost_activity_costs_t DEFAULT_ACTIVITY_COSTS = {
    0.0, 0.001, 0.002, 0.002, 0.08, 0.01, 0.12, 0.02,
    0.01, 0.10, 0.50, 0.001, 2.0, 0.01
};

static uint64_t territory_mix64(uint64_t value)
{
    value ^= value >> 30U;
    value *= UINT64_C(0xBF58476D1CE4E5B9);
    value ^= value >> 27U;
    value *= UINT64_C(0x94D049BB133111EB);
    return value ^ (value >> 31U);
}

typedef struct compost_sha256 {
    uint32_t state[8];
    uint8_t block[64];
    size_t used;
    uint64_t total;
} compost_sha256_t;

static uint32_t sha256_rotr(uint32_t value, uint32_t amount)
{
    return (value >> amount) | (value << (UINT32_C(32) - amount));
}

static void sha256_transform(compost_sha256_t *hash)
{
    static const uint32_t constants[64] = {
        UINT32_C(0x428A2F98), UINT32_C(0x71374491), UINT32_C(0xB5C0FBCF), UINT32_C(0xE9B5DBA5),
        UINT32_C(0x3956C25B), UINT32_C(0x59F111F1), UINT32_C(0x923F82A4), UINT32_C(0xAB1C5ED5),
        UINT32_C(0xD807AA98), UINT32_C(0x12835B01), UINT32_C(0x243185BE), UINT32_C(0x550C7DC3),
        UINT32_C(0x72BE5D74), UINT32_C(0x80DEB1FE), UINT32_C(0x9BDC06A7), UINT32_C(0xC19BF174),
        UINT32_C(0xE49B69C1), UINT32_C(0xEFBE4786), UINT32_C(0x0FC19DC6), UINT32_C(0x240CA1CC),
        UINT32_C(0x2DE92C6F), UINT32_C(0x4A7484AA), UINT32_C(0x5CB0A9DC), UINT32_C(0x76F988DA),
        UINT32_C(0x983E5152), UINT32_C(0xA831C66D), UINT32_C(0xB00327C8), UINT32_C(0xBF597FC7),
        UINT32_C(0xC6E00BF3), UINT32_C(0xD5A79147), UINT32_C(0x06CA6351), UINT32_C(0x14292967),
        UINT32_C(0x27B70A85), UINT32_C(0x2E1B2138), UINT32_C(0x4D2C6DFC), UINT32_C(0x53380D13),
        UINT32_C(0x650A7354), UINT32_C(0x766A0ABB), UINT32_C(0x81C2C92E), UINT32_C(0x92722C85),
        UINT32_C(0xA2BFE8A1), UINT32_C(0xA81A664B), UINT32_C(0xC24B8B70), UINT32_C(0xC76C51A3),
        UINT32_C(0xD192E819), UINT32_C(0xD6990624), UINT32_C(0xF40E3585), UINT32_C(0x106AA070),
        UINT32_C(0x19A4C116), UINT32_C(0x1E376C08), UINT32_C(0x2748774C), UINT32_C(0x34B0BCB5),
        UINT32_C(0x391C0CB3), UINT32_C(0x4ED8AA4A), UINT32_C(0x5B9CCA4F), UINT32_C(0x682E6FF3),
        UINT32_C(0x748F82EE), UINT32_C(0x78A5636F), UINT32_C(0x84C87814), UINT32_C(0x8CC70208),
        UINT32_C(0x90BEFFFA), UINT32_C(0xA4506CEB), UINT32_C(0xBEF9A3F7), UINT32_C(0xC67178F2)
    };
    uint32_t words[64] = {0};
    for (size_t index = 0U; index < 16U; ++index) {
        const size_t offset = index * 4U;
        words[index] = ((uint32_t)hash->block[offset] << 24U) |
            ((uint32_t)hash->block[offset + 1U] << 16U) |
            ((uint32_t)hash->block[offset + 2U] << 8U) |
            (uint32_t)hash->block[offset + 3U];
    }
    for (size_t index = 16U; index < 64U; ++index) {
        const uint32_t first = words[index - 15U];
        const uint32_t second = words[index - 2U];
        const uint32_t small_first = sha256_rotr(first, 7U) ^ sha256_rotr(first, 18U) ^ (first >> 3U);
        const uint32_t small_second = sha256_rotr(second, 17U) ^ sha256_rotr(second, 19U) ^ (second >> 10U);
        words[index] = words[index - 16U] + small_first + words[index - 7U] + small_second;
    }
    uint32_t a = hash->state[0];
    uint32_t b = hash->state[1];
    uint32_t c = hash->state[2];
    uint32_t d = hash->state[3];
    uint32_t e = hash->state[4];
    uint32_t f = hash->state[5];
    uint32_t g = hash->state[6];
    uint32_t h = hash->state[7];
    for (size_t index = 0U; index < 64U; ++index) {
        const uint32_t big_e = sha256_rotr(e, 6U) ^ sha256_rotr(e, 11U) ^ sha256_rotr(e, 25U);
        const uint32_t choose = (e & f) ^ ((~e) & g);
        const uint32_t big_a = sha256_rotr(a, 2U) ^ sha256_rotr(a, 13U) ^ sha256_rotr(a, 22U);
        const uint32_t majority = (a & b) ^ (a & c) ^ (b & c);
        const uint32_t first = h + big_e + choose + constants[index] + words[index];
        const uint32_t second = big_a + majority;
        h = g;
        g = f;
        f = e;
        e = d + first;
        d = c;
        c = b;
        b = a;
        a = first + second;
    }
    hash->state[0] += a;
    hash->state[1] += b;
    hash->state[2] += c;
    hash->state[3] += d;
    hash->state[4] += e;
    hash->state[5] += f;
    hash->state[6] += g;
    hash->state[7] += h;
}

static void sha256_init(compost_sha256_t *hash)
{
    *hash = (compost_sha256_t){
        {UINT32_C(0x6A09E667), UINT32_C(0xBB67AE85), UINT32_C(0x3C6EF372), UINT32_C(0xA54FF53A),
         UINT32_C(0x510E527F), UINT32_C(0x9B05688C), UINT32_C(0x1F83D9AB), UINT32_C(0x5BE0CD19)},
        {0}, 0U, 0U
    };
}

static void sha256_update(compost_sha256_t *hash, const uint8_t *data, size_t length)
{
    while (length > 0U) {
        const size_t available = 64U - hash->used;
        const size_t amount = length < available ? length : available;
        memcpy(&hash->block[hash->used], data, amount);
        hash->used += amount;
        data += amount;
        length -= amount;
        hash->total += (uint64_t)amount;
        if (hash->used == 64U) {
            sha256_transform(hash);
            hash->used = 0U;
        }
    }
}

static void sha256_final(compost_sha256_t *hash, uint8_t output[32])
{
    const uint64_t bits = hash->total * UINT64_C(8);
    hash->block[hash->used++] = UINT8_C(0x80);
    if (hash->used > 56U) {
        while (hash->used < 64U) hash->block[hash->used++] = 0U;
        sha256_transform(hash);
        hash->used = 0U;
    }
    while (hash->used < 56U) hash->block[hash->used++] = 0U;
    for (size_t index = 0U; index < 8U; ++index) {
        hash->block[56U + index] = (uint8_t)(bits >> (56U - index * 8U));
    }
    sha256_transform(hash);
    for (size_t index = 0U; index < 8U; ++index) {
        output[index * 4U] = (uint8_t)(hash->state[index] >> 24U);
        output[index * 4U + 1U] = (uint8_t)(hash->state[index] >> 16U);
        output[index * 4U + 2U] = (uint8_t)(hash->state[index] >> 8U);
        output[index * 4U + 3U] = (uint8_t)hash->state[index];
    }
}

compost_status_t compost_territory_address_bit(
    uint64_t address,
    uint32_t depth,
    uint8_t *bit
)
{
    if (bit == NULL || depth >= COMPOST_MAX_TERRITORY_DEPTH) {
        return COMPOST_STATUS_INVALID_ARGUMENT;
    }
    const uint64_t salt = (uint64_t)(depth + UINT32_C(1)) * UINT64_C(0x9E3779B97F4A7C15);
    *bit = (uint8_t)(territory_mix64(address ^ salt) & UINT64_C(1));
    return COMPOST_STATUS_OK;
}

compost_status_t compost_territory_contains(
    const uint8_t *path,
    size_t depth,
    uint64_t address,
    bool *contains
)
{
    if (contains == NULL || depth > COMPOST_MAX_TERRITORY_DEPTH ||
        (depth > 0U && path == NULL)) {
        return COMPOST_STATUS_INVALID_ARGUMENT;
    }
    bool result = true;
    for (size_t index = 0U; index < depth; ++index) {
        if (path[index] > UINT8_C(1)) return COMPOST_STATUS_INVALID_ARGUMENT;
        uint8_t bit = 0U;
        if (compost_territory_address_bit(address, (uint32_t)index, &bit) != COMPOST_STATUS_OK) {
            return COMPOST_STATUS_INVALID_ARGUMENT;
        }
        if (bit != path[index]) result = false;
    }
    *contains = result;
    return COMPOST_STATUS_OK;
}

compost_status_t compost_territory_food_block_key(
    const uint8_t *file_id,
    size_t file_id_length,
    uint64_t block_index,
    uint64_t *key
)
{
    if (key == NULL || (file_id_length > 0U && file_id == NULL) ||
        file_id_length > (size_t)(UINT64_MAX / UINT64_C(8) - UINT64_C(9))) {
        return COMPOST_STATUS_INVALID_ARGUMENT;
    }
    compost_sha256_t hash = {0};
    uint8_t digest[32] = {0};
    const uint8_t separator = 0U;
    uint8_t block_bytes[8] = {0};
    for (size_t index = 0U; index < 8U; ++index) {
        block_bytes[index] = (uint8_t)(block_index >> (56U - index * 8U));
    }
    sha256_init(&hash);
    sha256_update(&hash, file_id, file_id_length);
    sha256_update(&hash, &separator, 1U);
    sha256_update(&hash, block_bytes, sizeof(block_bytes));
    sha256_final(&hash, digest);
    uint64_t result = 0U;
    for (size_t index = 0U; index < 8U; ++index) {
        result = (result << 8U) | (uint64_t)digest[index];
    }
    *key = result;
    return COMPOST_STATUS_OK;
}

static bool valid_config(const compost_config_t *config)
{
    return config != NULL &&
           config->abi_version == COMPOST_NATIVE_ABI_VERSION &&
           config->max_body_mass > 0U &&
           config->max_territory_depth <= COMPOST_MAX_TERRITORY_DEPTH &&
           config->income_decay > 0.0 && config->income_decay < 1.0 &&
           finite(config->atom_income) && config->atom_income > 0.0 &&
           finite(config->relation_income) && config->relation_income > 0.0 &&
           finite(config->composite_income) && config->composite_income > 0.0 &&
           finite(config->atom_maintenance) && config->atom_maintenance > 0.0 &&
           finite(config->relation_maintenance) && config->relation_maintenance > 0.0 &&
           finite(config->composite_maintenance) && config->composite_maintenance > 0.0 &&
           finite(config->atom_formation_cost) && config->atom_formation_cost > 0.0 &&
           finite(config->relation_formation_cost) && config->relation_formation_cost > 0.0 &&
           finite(config->consolidation_formation_cost) && config->consolidation_formation_cost > 0.0 &&
           finite(config->birth_cost) && config->birth_cost > 0.0 &&
           finite(config->division_horizon) && config->division_horizon > 0.0 &&
           finite(config->boundary_ratio_limit) && config->boundary_ratio_limit > 0.0 &&
           config->boundary_ratio_limit < 1.0 &&
           config->reproduction_minimum_body > 0U &&
           finite(config->birth_reserve) && config->birth_reserve >= 0.0;
}

compost_status_t compost_create(
    const compost_config_t *config,
    uint64_t organism_id,
    compost_context_t **context
)
{
    return compost_create_with_allocator(config, NULL, organism_id, context);
}

compost_status_t compost_create_with_allocator(
    const compost_config_t *config,
    const compost_allocator_t *allocator,
    uint64_t organism_id,
    compost_context_t **context
)
{
    if (context == NULL || !valid_config(config) || !valid_allocator(allocator)) {
        return COMPOST_STATUS_INVALID_ARGUMENT;
    }
    *context = NULL;
    const compost_allocator_t effective = effective_allocator(allocator);
    compost_context_t *created = effective.allocate(effective.context, sizeof(*created));
    if (created == NULL) {
        return COMPOST_STATUS_OUT_OF_MEMORY;
    }
    memset(created, 0, sizeof(*created));
    created->allocator = effective;
    const compost_status_t status = compost_organism_init(&created->organism, config, &effective, organism_id);
    if (status != COMPOST_STATUS_OK) {
        effective.deallocate(effective.context, created);
        return status;
    }
    *context = created;
    return COMPOST_STATUS_OK;
}

void compost_destroy(compost_context_t *context)
{
    if (context == NULL) return;
    const compost_allocator_t allocator = context->allocator;
    compost_organism_destroy(&context->organism);
    allocator.deallocate(allocator.context, context);
}

compost_status_t compost_context_snapshot(
    const compost_context_t *context,
    compost_snapshot_t *snapshot
)
{
    if (context == NULL) return COMPOST_STATUS_INVALID_ARGUMENT;
    return compost_organism_snapshot(&context->organism, snapshot);
}

uint64_t compost_context_state_digest(const compost_context_t *context)
{
    if (context == NULL) {
        return UINT64_C(0);
    }
    uint64_t digest = compost_organism_state_digest(&context->organism);
    digest = digest_u64(digest, context->metabolic_progress);
    return digest_u64(digest, context->metabolic_steps);
}

compost_status_t compost_context_metabolic_snapshot(
    const compost_context_t *context,
    compost_metabolic_snapshot_t *snapshot
)
{
    if (context == NULL || snapshot == NULL) return COMPOST_STATUS_INVALID_ARGUMENT;
    snapshot->progress = context->metabolic_progress;
    snapshot->steps = context->metabolic_steps;
    return COMPOST_STATUS_OK;
}

compost_status_t compost_context_accumulate_metabolic_progress(
    compost_context_t *context,
    uint64_t amount,
    uint64_t minimum_work,
    uint64_t body_size,
    uint64_t *due_steps,
    uint64_t *remaining_progress
)
{
    if (context == NULL || due_steps == NULL || remaining_progress == NULL || minimum_work == 0U) {
        return COMPOST_STATUS_INVALID_ARGUMENT;
    }
    if (UINT64_MAX - context->metabolic_progress < amount) {
        return COMPOST_STATUS_INVALID_ARGUMENT;
    }
    const uint64_t accumulated = context->metabolic_progress + amount;
    uint64_t threshold = 0U;
    uint64_t settled = 0U;
    uint64_t remainder = 0U;
    compost_status_t status = compost_metabolic_schedule(
        minimum_work, body_size, accumulated, &threshold, &settled, &remainder
    );
    if (status != COMPOST_STATUS_OK || UINT64_MAX - context->metabolic_steps < settled) {
        return status == COMPOST_STATUS_OK ? COMPOST_STATUS_INVALID_ARGUMENT : status;
    }
    context->metabolic_progress = remainder;
    context->metabolic_steps += settled;
    *due_steps = settled;
    *remaining_progress = remainder;
    return COMPOST_STATUS_OK;
}

compost_status_t compost_context_digest(
    compost_context_t *context,
    const compost_step_input_t *input,
    compost_step_result_t *result
)
{
    if (context == NULL) return COMPOST_STATUS_INVALID_ARGUMENT;
    return compost_organism_digest(&context->organism, input, result);
}

compost_status_t compost_context_step(
    compost_context_t *context,
    const compost_step_input_t *input,
    compost_cycle_result_t *result
)
{
    if (context == NULL) return COMPOST_STATUS_INVALID_ARGUMENT;
    return compost_organism_step(&context->organism, input, result);
}

compost_status_t compost_context_lifecycle_step(
    compost_context_t *context,
    const compost_step_input_t *input,
    compost_cycle_result_t *result
)
{
    if (context == NULL || input == NULL || result == NULL) return COMPOST_STATUS_INVALID_ARGUMENT;
    compost_context_t next = *context;
    if (!next.organism.initialized ||
        (input->length > 0U && (input->food == NULL || input->nutrition == NULL))) {
        return COMPOST_STATUS_INVALID_ARGUMENT;
    }
    if (next.organism.status == COMPOST_LIFECYCLE_DEAD) {
        *result = (compost_cycle_result_t){0};
        result->status_after = COMPOST_LIFECYCLE_DEAD;
        return COMPOST_STATUS_OK;
    }
    compost_cycle_result_t next_result = {0};
    compost_status_t status = compost_organism_digest(&next.organism, input, &next_result.digestion);
    if (status != COMPOST_STATUS_OK) return status;
    const uint64_t lifecycle_mass_before = next.organism.body.structural_mass;
    const uint64_t lifecycle_resorptions_before = next.organism.activity.counters.resorption_events;
    status = compost_organism_consolidate(
        &next.organism,
        next.organism.config.composite_maintenance,
        next.organism.config.consolidation_formation_cost,
        &next_result.composites_consolidated
    );
    if (status != COMPOST_STATUS_OK) return status;
    status = lifecycle_maintenance(&next.organism, &next_result.maintenance);
    if (status != COMPOST_STATUS_OK) return status;
    compost_activity_counters_t lifecycle_counters = {0};
    lifecycle_counters.composites_created = next_result.composites_consolidated;
    if (next.organism.body.structural_mass >= lifecycle_mass_before) {
        lifecycle_counters.structural_mass_added = next.organism.body.structural_mass - lifecycle_mass_before;
    } else {
        lifecycle_counters.structural_mass_lost = lifecycle_mass_before - next.organism.body.structural_mass;
    }
    if (next.organism.activity.counters.resorption_events >= lifecycle_resorptions_before) {
        lifecycle_counters.resorption_events =
            next.organism.activity.counters.resorption_events - lifecycle_resorptions_before;
    }
    status = activity_charge_only(&next.organism.activity, &lifecycle_counters, &DEFAULT_ACTIVITY_COSTS);
    if (status != COMPOST_STATUS_OK) return status;
    next_result.status_after = next.organism.status;
    *result = next_result;
    status = settle_activity_debt(&next.organism);
    if (status != COMPOST_STATUS_OK) return status;
    *context = next;
    return COMPOST_STATUS_OK;
}

compost_status_t compost_context_step_and_try_divide(
    compost_context_t *context,
    const compost_step_input_t *input,
    uint64_t child_id,
    compost_context_t **child,
    compost_cycle_result_t *cycle_result,
    compost_division_plan_t *plan,
    compost_division_result_t *division_result
)
{
    if (context == NULL || input == NULL || child == NULL || cycle_result == NULL ||
        plan == NULL || division_result == NULL) {
        return COMPOST_STATUS_INVALID_ARGUMENT;
    }
    compost_context_t working = *context;
    compost_cycle_result_t next_cycle = {0};
    compost_division_plan_t next_plan = {0};
    compost_division_result_t next_division = {0};
    compost_status_t status = compost_organism_step(&working.organism, input, &next_cycle);
    if (status != COMPOST_STATUS_OK) return status;
    if (working.organism.status == COMPOST_LIFECYCLE_ALIVE) {
        status = compost_organism_plan_division(&working.organism, &next_plan);
        if (status != COMPOST_STATUS_OK) return status;
    }
    compost_context_t *created = NULL;
    if (next_plan.candidate_found && next_plan.allowed) {
        created = working.allocator.allocate(working.allocator.context, sizeof(*created));
        if (created == NULL) return COMPOST_STATUS_OUT_OF_MEMORY;
        memset(created, 0, sizeof(*created));
        created->allocator = working.allocator;
        status = compost_organism_partition(
            &working.organism,
            &created->organism,
            child_id,
            next_plan.child_atoms,
            next_plan.child_atom_count,
            working.organism.config.birth_cost,
            &next_division
        );
        if (status != COMPOST_STATUS_OK) {
            working.allocator.deallocate(working.allocator.context, created);
            return status;
        }
    }
    context->organism = working.organism;
    *child = created;
    *cycle_result = next_cycle;
    *plan = next_plan;
    *division_result = next_division;
    return COMPOST_STATUS_OK;
}

compost_status_t compost_context_enqueue_external(
    compost_context_t *context,
    const compost_step_input_t *input
)
{
    if (context == NULL) return COMPOST_STATUS_INVALID_ARGUMENT;
    return compost_organism_enqueue_external(&context->organism, input);
}

compost_status_t compost_context_process_gut(
    compost_context_t *context,
    uint64_t capacity,
    compost_gut_process_result_t *result
)
{
    if (context == NULL) return COMPOST_STATUS_INVALID_ARGUMENT;
    return compost_organism_process_gut(&context->organism, capacity, result);
}

compost_status_t compost_context_weaken_weakest(
    compost_context_t *context,
    bool *changed,
    uint64_t *resorbed_mass
)
{
    if (context == NULL) return COMPOST_STATUS_INVALID_ARGUMENT;
    return compost_organism_weaken_weakest(&context->organism, changed, resorbed_mass);
}

compost_status_t compost_context_verify_material_conservation(
    const compost_context_t *context
)
{
    if (context == NULL) return COMPOST_STATUS_INVALID_ARGUMENT;
    return compost_organism_verify_material_conservation(&context->organism);
}

static compost_status_t compost_organism_apply_corpse_energy(
    compost_organism_t *organism,
    double energy,
    double *credited
)
{
    if (organism == NULL || credited == NULL || !organism->initialized ||
        organism->status != COMPOST_LIFECYCLE_ALIVE || !finite(energy) || energy < 0.0) {
        return COMPOST_STATUS_INVALID_ARGUMENT;
    }
    compost_organism_t next = *organism;
    if (!add_double(next.reserve, energy, &next.reserve)) return COMPOST_STATUS_INVALID_ARGUMENT;
    *organism = next;
    *credited = energy;
    return COMPOST_STATUS_OK;
}

compost_status_t compost_context_apply_corpse_energy(
    compost_context_t *context,
    double energy,
    double *credited
)
{
    if (context == NULL) return COMPOST_STATUS_INVALID_ARGUMENT;
    return compost_organism_apply_corpse_energy(&context->organism, energy, credited);
}

compost_status_t compost_context_partition(
    compost_context_t *parent,
    uint64_t child_id,
    const uint8_t *child_atoms,
    size_t child_atom_count,
    double birth_cost,
    compost_context_t **child,
    compost_division_result_t *result
)
{
    if (parent == NULL || child == NULL || result == NULL) {
        return COMPOST_STATUS_INVALID_ARGUMENT;
    }
    *child = NULL;
    const compost_allocator_t allocator = parent->allocator;
    compost_context_t *created = allocator.allocate(allocator.context, sizeof(*created));
    if (created == NULL) {
        return COMPOST_STATUS_OUT_OF_MEMORY;
    }
    memset(created, 0, sizeof(*created));
    created->allocator = allocator;
    const compost_status_t status = compost_organism_partition(
        &parent->organism,
        &created->organism,
        child_id,
        child_atoms,
        child_atom_count,
        birth_cost,
        result
    );
    if (status != COMPOST_STATUS_OK) {
        allocator.deallocate(allocator.context, created);
        return status;
    }
    *child = created;
    return COMPOST_STATUS_OK;
}

compost_status_t compost_context_select_partition(
    const compost_context_t *context,
    double boundary_ratio_limit,
    uint8_t *child_atoms,
    size_t child_atom_capacity,
    size_t *child_atom_count,
    double *selected_ratio
)
{
    if (context == NULL) return COMPOST_STATUS_INVALID_ARGUMENT;
    return compost_organism_select_partition(
        &context->organism,
        boundary_ratio_limit,
        child_atoms,
        child_atom_capacity,
        child_atom_count,
        selected_ratio
    );
}

compost_status_t compost_context_select_local_reproduction(
    const compost_context_t *context,
    uint8_t *child_atoms,
    size_t child_atom_capacity,
    size_t *child_atom_count
)
{
    if (context == NULL) return COMPOST_STATUS_INVALID_ARGUMENT;
    return compost_organism_select_local_reproduction(
        &context->organism,
        child_atoms,
        child_atom_capacity,
        child_atom_count
    );
}

compost_status_t compost_context_plan_division(
    const compost_context_t *context,
    compost_division_plan_t *plan
)
{
    if (context == NULL) return COMPOST_STATUS_INVALID_ARGUMENT;
    return compost_organism_plan_division(&context->organism, plan);
}

compost_status_t compost_context_try_divide(
    compost_context_t *parent,
    uint64_t child_id,
    compost_context_t **child,
    compost_division_plan_t *plan,
    compost_division_result_t *result
)
{
    if (parent == NULL || child == NULL || plan == NULL || result == NULL) {
        return COMPOST_STATUS_INVALID_ARGUMENT;
    }
    *child = NULL;
    memset(plan, 0, sizeof(*plan));
    memset(result, 0, sizeof(*result));
    const compost_status_t status = compost_organism_plan_division(&parent->organism, plan);
    if (status != COMPOST_STATUS_OK || !plan->candidate_found || !plan->allowed) {
        return status;
    }
    return compost_context_partition(
        parent,
        child_id,
        plan->child_atoms,
        plan->child_atom_count,
        parent->organism.config.birth_cost,
        child,
        result
    );
}

compost_status_t compost_context_try_local_reproduction(
    compost_context_t *parent,
    uint64_t child_id,
    compost_context_t **child,
    compost_division_result_t *result
)
{
    if (parent == NULL || child == NULL || result == NULL) {
        return COMPOST_STATUS_INVALID_ARGUMENT;
    }
    *child = NULL;
    memset(result, 0, sizeof(*result));
    uint8_t child_atoms[COMPOST_MAX_ATOMS] = {0U};
    size_t child_atom_count = 0U;
    const compost_status_t selection = compost_organism_select_local_reproduction(
        &parent->organism,
        child_atoms,
        COMPOST_MAX_ATOMS,
        &child_atom_count
    );
    if (selection == COMPOST_STATUS_INVALID_STATE) return COMPOST_STATUS_OK;
    if (selection != COMPOST_STATUS_OK) return selection;
    return compost_context_partition(
        parent,
        child_id,
        child_atoms,
        child_atom_count,
        parent->organism.config.birth_cost,
        child,
        result
    );
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
    config->atom_income = 1.0;
    config->relation_income = 0.8;
    config->composite_income = 1.1;
    config->atom_maintenance = 0.25;
    config->relation_maintenance = 0.5;
    config->composite_maintenance = 0.3;
    config->atom_formation_cost = 0.35;
    config->relation_formation_cost = 1.25;
    config->consolidation_formation_cost = 1.5;
    config->birth_cost = 1.0;
    config->division_horizon = 8.0;
    config->boundary_ratio_limit = 0.15;
    config->birth_reserve = 1.0;
    config->reproduction_minimum_body = 32U;
    return COMPOST_STATUS_OK;
}

compost_status_t compost_organism_init(
    compost_organism_t *organism,
    const compost_config_t *config,
    const compost_allocator_t *allocator,
    uint64_t organism_id
)
{
    if (organism == NULL || !valid_config(config) || !valid_allocator(allocator) ||
        config->max_body_mass < UINT64_C(256)) {
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
    organism->reserve = config->birth_reserve;
    organism->body.structural_mass = UINT64_C(256);
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

static compost_status_t validate_gut(const compost_organism_t *organism)
{
    if (organism->gut_head >= COMPOST_MAX_GUT_CHUNKS ||
        organism->gut_count > COMPOST_MAX_GUT_CHUNKS) {
        return COMPOST_STATUS_INVALID_STATE;
    }
    for (size_t index = 0U; index < COMPOST_MAX_GUT_CHUNKS; ++index) {
        const compost_gut_chunk_t *chunk = &organism->gut[index];
        if (chunk->origin == COMPOST_MATERIAL_EXTERNAL) {
            if (chunk->payload_length > COMPOST_MAX_GUT_CHUNK_BYTES ||
                chunk->payload_length != chunk->mass) {
                return COMPOST_STATUS_INVALID_STATE;
            }
            for (size_t byte = 0U; byte < chunk->payload_length; ++byte) {
                if (!finite(chunk->nutrition[byte])) return COMPOST_STATUS_INVALID_STATE;
            }
        } else if (chunk->origin == COMPOST_MATERIAL_RESORPTION) {
            if (chunk->payload_length != 0U) return COMPOST_STATUS_INVALID_STATE;
        } else {
            return COMPOST_STATUS_INVALID_STATE;
        }
    }
    return COMPOST_STATUS_OK;
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
    if (organism->status != COMPOST_LIFECYCLE_ALIVE &&
        organism->status != COMPOST_LIFECYCLE_DEAD) {
        return COMPOST_STATUS_INVALID_STATE;
    }
    if (validate_gut(organism) != COMPOST_STATUS_OK) {
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
    memcpy(snapshot->atoms, organism->atoms, sizeof(snapshot->atoms));
    memcpy(snapshot->relations, organism->relations, sizeof(snapshot->relations));
    memcpy(snapshot->composites, organism->composites, sizeof(snapshot->composites));
    memcpy(snapshot->activated_receptors, organism->activated_receptors, sizeof(snapshot->activated_receptors));
    memcpy(snapshot->gut, organism->gut, sizeof(snapshot->gut));
    snapshot->gut_head = organism->gut_head;
    snapshot->gut_count = organism->gut_count;
    return COMPOST_STATUS_OK;
}

static uint64_t digest_bytes(uint64_t digest, const void *data, size_t length)
{
    const unsigned char *bytes = data;
    for (size_t index = 0U; index < length; ++index) {
        digest ^= (uint64_t)bytes[index];
        digest *= UINT64_C(1099511628211);
    }
    return digest;
}

static uint64_t digest_u8(uint64_t digest, uint8_t value)
{
    return digest_bytes(digest, &value, sizeof(value));
}

static uint64_t digest_u32(uint64_t digest, uint32_t value)
{
    for (unsigned int shift = 0U; shift < 32U; shift += 8U) {
        digest = digest_u8(digest, (uint8_t)((value >> shift) & UINT32_C(0xff)));
    }
    return digest;
}

static uint64_t digest_u64(uint64_t digest, uint64_t value)
{
    for (unsigned int shift = 0U; shift < 64U; shift += 8U) {
        digest = digest_u8(digest, (uint8_t)((value >> shift) & UINT64_C(0xff)));
    }
    return digest;
}

static uint64_t digest_bool(uint64_t digest, bool value)
{
    return digest_u8(digest, value ? UINT8_C(1) : UINT8_C(0));
}

static uint64_t digest_double(uint64_t digest, double value)
{
    uint64_t bits = 0U;
    memcpy(&bits, &value, sizeof(bits));
    return digest_u64(digest, bits);
}

static uint64_t digest_structure(uint64_t digest, const compost_structure_t *structure)
{
    digest = digest_bool(digest, structure->occupied);
    digest = digest_u32(digest, (uint32_t)structure->kind);
    digest = digest_u8(digest, structure->left);
    digest = digest_u8(digest, structure->right);
    digest = digest_double(digest, structure->strength);
    digest = digest_double(digest, structure->maintenance);
    digest = digest_double(digest, structure->evidence);
    return digest_double(digest, structure->income_rate);
}

static uint64_t digest_config(uint64_t digest, const compost_config_t *config)
{
    digest = digest_u32(digest, config->abi_version);
    digest = digest_u64(digest, config->seed);
    digest = digest_u64(digest, config->max_body_mass);
    digest = digest_u32(digest, config->max_territory_depth);
    digest = digest_double(digest, config->income_decay);
    digest = digest_double(digest, config->atom_income);
    digest = digest_double(digest, config->relation_income);
    digest = digest_double(digest, config->composite_income);
    digest = digest_double(digest, config->atom_maintenance);
    digest = digest_double(digest, config->relation_maintenance);
    digest = digest_double(digest, config->composite_maintenance);
    digest = digest_double(digest, config->atom_formation_cost);
    digest = digest_double(digest, config->relation_formation_cost);
    digest = digest_double(digest, config->consolidation_formation_cost);
    digest = digest_double(digest, config->birth_cost);
    digest = digest_double(digest, config->division_horizon);
    digest = digest_double(digest, config->boundary_ratio_limit);
    digest = digest_double(digest, config->birth_reserve);
    return digest_u64(digest, config->reproduction_minimum_body);
}

static uint64_t digest_material_flow(uint64_t digest, const compost_material_flow_t *flow)
{
    digest = digest_u64(digest, flow->input_mass);
    digest = digest_u64(digest, flow->assimilated_mass);
    digest = digest_u64(digest, flow->rejected_mass);
    digest = digest_u64(digest, flow->resorbed_mass);
    digest = digest_u64(digest, flow->processed_mass);
    digest = digest_u64(digest, flow->expelled_mass);
    digest = digest_u64(digest, flow->external_expelled_mass);
    digest = digest_u64(digest, flow->resorption_expelled_mass);
    digest = digest_u64(digest, flow->structural_created_mass);
    digest = digest_u64(digest, flow->structural_transferred_in);
    return digest_u64(digest, flow->structural_transferred_out);
}

static uint64_t digest_activity(uint64_t digest, const compost_activity_ledger_t *activity)
{
    digest = digest_double(digest, activity->metabolic_debt);
    digest = digest_double(digest, activity->energy_spent);
    digest = digest_u64(digest, activity->settlements);
    digest = digest_u64(digest, activity->counters.bytes_eaten);
    digest = digest_u64(digest, activity->counters.relations_created);
    digest = digest_u64(digest, activity->counters.relations_strengthened);
    digest = digest_u64(digest, activity->counters.composites_created);
    digest = digest_u64(digest, activity->counters.composites_strengthened);
    digest = digest_u64(digest, activity->counters.structural_mass_added);
    digest = digest_u64(digest, activity->counters.structural_mass_lost);
    digest = digest_u64(digest, activity->counters.resorption_events);
    digest = digest_u64(digest, activity->counters.division_events);
    digest = digest_u64(digest, activity->counters.processed_bytes);
    digest = digest_u64(digest, activity->counters.rejected_bytes);
    return digest_u64(digest, activity->counters.resorbed_processed_bytes);
}

uint64_t compost_organism_state_digest(const compost_organism_t *organism)
{
    if (organism == NULL || !organism->initialized) {
        return UINT64_C(0);
    }
    uint64_t digest = UINT64_C(1469598103934665603);
    digest = digest_config(digest, &organism->config);
    digest = digest_u64(digest, organism->organism_id);
    digest = digest_u64(digest, organism->parent_id);
    digest = digest_bool(digest, organism->has_parent);
    digest = digest_u64(digest, organism->generation);
    digest = digest_u64(digest, organism->cursor);
    digest = digest_u64(digest, organism->age_in_cycles);
    digest = digest_u32(digest, (uint32_t)organism->status);
    digest = digest_double(digest, organism->reserve);
    digest = digest_u64(digest, organism->body.structural_mass);
    digest = digest_u64(digest, organism->body.atom_count);
    digest = digest_u64(digest, organism->body.relation_count);
    digest = digest_u64(digest, organism->body.composite_count);
    digest = digest_material_flow(digest, &organism->material_flow);
    digest = digest_activity(digest, &organism->activity);
    digest = digest_bytes(digest, organism->territory.path, sizeof(organism->territory.path));
    digest = digest_u32(digest, organism->territory.depth);
    digest = digest_u64(digest, organism->territory.organism_id);
    digest = digest_u64(digest, organism->territory.local_birth_counter);
    digest = digest_bool(digest, organism->territory.alive);
    for (size_t index = 0U; index < COMPOST_MAX_ATOMS; ++index) digest = digest_structure(digest, &organism->atoms[index]);
    for (size_t index = 0U; index < COMPOST_MAX_RELATIONS; ++index) digest = digest_structure(digest, &organism->relations[index]);
    for (size_t index = 0U; index < COMPOST_MAX_COMPOSITES; ++index) digest = digest_structure(digest, &organism->composites[index]);
    for (size_t index = 0U; index < 4U; ++index) digest = digest_u64(digest, organism->activated_receptors[index]);
    for (size_t index = 0U; index < COMPOST_MAX_GUT_CHUNKS; ++index) {
        digest = digest_u64(digest, organism->gut[index].mass);
        digest = digest_u32(digest, (uint32_t)organism->gut[index].origin);
        digest = digest_u32(digest, organism->gut[index].payload_length);
        for (size_t byte = 0U; byte < COMPOST_MAX_GUT_CHUNK_BYTES; ++byte) {
            digest = digest_u8(digest, organism->gut[index].payload[byte]);
            digest = digest_double(digest, organism->gut[index].nutrition[byte]);
        }
    }
    digest = digest_u32(digest, organism->gut_head);
    return digest_u32(digest, organism->gut_count);
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

compost_status_t compost_metabolic_schedule(
    uint64_t minimum_work,
    uint64_t body_size,
    uint64_t progress,
    uint64_t *threshold,
    uint64_t *due_steps,
    uint64_t *remaining_progress
)
{
    if (minimum_work == 0U || threshold == NULL || due_steps == NULL ||
        remaining_progress == NULL) {
        return COMPOST_STATUS_INVALID_ARGUMENT;
    }
    const uint64_t next_threshold = minimum_work > body_size ? minimum_work : body_size;
    *threshold = next_threshold;
    *due_steps = progress / next_threshold;
    *remaining_progress = progress % next_threshold;
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
    double delta = 0.0;
    if (activity_delta(counters, costs, &delta) != COMPOST_STATUS_OK ||
        !finite(next.metabolic_debt + delta)) {
        return COMPOST_STATUS_INVALID_ARGUMENT;
    }
    next.metabolic_debt += delta;
    *ledger = next;
    return COMPOST_STATUS_OK;
}

static compost_status_t activity_delta(
    const compost_activity_counters_t *counters,
    const compost_activity_costs_t *costs,
    double *delta
)
{
    if (counters == NULL || !valid_costs(costs) || delta == NULL) {
        return COMPOST_STATUS_INVALID_ARGUMENT;
    }
    const double kib = 1024.0;
    const double value =
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
    if (!finite(value)) return COMPOST_STATUS_INVALID_ARGUMENT;
    *delta = value;
    return COMPOST_STATUS_OK;
}

static compost_status_t activity_charge_only(
    compost_activity_ledger_t *ledger,
    const compost_activity_counters_t *counters,
    const compost_activity_costs_t *costs
)
{
    if (ledger == NULL || counters == NULL || !valid_costs(costs)) {
        return COMPOST_STATUS_INVALID_ARGUMENT;
    }
    double delta = 0.0;
    if (activity_delta(counters, costs, &delta) != COMPOST_STATUS_OK ||
        !finite(ledger->metabolic_debt + delta)) {
        return COMPOST_STATUS_INVALID_ARGUMENT;
    }
    ledger->metabolic_debt += delta;
    return COMPOST_STATUS_OK;
}

static compost_status_t settle_activity_debt(compost_organism_t *organism)
{
    if (organism == NULL || !organism->initialized) return COMPOST_STATUS_INVALID_ARGUMENT;
    const double threshold = DEFAULT_ACTIVITY_COSTS.settlement_base +
        DEFAULT_ACTIVITY_COSTS.settlement_mass_scale * (double)organism->body.structural_mass;
    if (!finite(threshold) || organism->activity.metabolic_debt < threshold) {
        return COMPOST_STATUS_OK;
    }
    double debt_with_basal = 0.0;
    if (!add_double(organism->activity.metabolic_debt,
                    DEFAULT_ACTIVITY_COSTS.basal_mass * (double)organism->body.structural_mass,
                    &debt_with_basal)) {
        return COMPOST_STATUS_INVALID_ARGUMENT;
    }
    const double paid = organism->reserve < debt_with_basal ? organism->reserve : debt_with_basal;
    organism->reserve -= paid;
    organism->activity.metabolic_debt = debt_with_basal - paid;
    if (paid > 0.0) {
        if (!add_double(organism->activity.energy_spent, paid, &organism->activity.energy_spent) ||
            organism->activity.settlements == UINT64_MAX) {
            return COMPOST_STATUS_INVALID_ARGUMENT;
        }
        organism->activity.settlements += UINT64_C(1);
    }
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

compost_status_t compost_lazy_metabolism_delta(
    double strength,
    double income_rate,
    double maintenance,
    double income_decay,
    uint64_t epochs,
    compost_lazy_metabolism_delta_t *delta
)
{
    if (delta == NULL || !finite(strength) || !finite(income_rate) ||
        !finite(maintenance) || !finite(income_decay) || maintenance < 0.0 ||
        !(income_decay > 0.0 && income_decay < 1.0)) {
        return COMPOST_STATUS_INVALID_ARGUMENT;
    }
    uint64_t decay_epochs = 0U;
    if (epochs > 0U) {
        if (income_rate <= maintenance) {
            decay_epochs = epochs;
        } else if (maintenance > 0.0) {
            const double first_real = ceil(log(maintenance / income_rate) / log(income_decay));
            if (!finite(first_real) || first_real < 0.0) {
                return COMPOST_STATUS_INVALID_ARGUMENT;
            }
            if (first_real < (double)epochs) {
                decay_epochs = (uint64_t)first_real;
                while (decay_epochs > 0U &&
                       income_rate * pow(income_decay, (double)(decay_epochs - 1U)) <= maintenance) {
                    --decay_epochs;
                }
                while (decay_epochs < epochs &&
                       income_rate * pow(income_decay, (double)decay_epochs) > maintenance) {
                    ++decay_epochs;
                }
                decay_epochs = epochs - decay_epochs;
            }
        }
    }
    delta->strength_after = fmax(1.0, strength * pow(income_decay, (double)decay_epochs));
    delta->income_rate_after = income_rate * pow(income_decay, (double)epochs);
    delta->strength_decay_epochs = decay_epochs;
    return finite(delta->strength_after) && finite(delta->income_rate_after)
        ? COMPOST_STATUS_OK : COMPOST_STATUS_INVALID_ARGUMENT;
}

compost_status_t compost_reproduction_assessment(
    uint64_t body_size,
    double parent_reserve,
    double birth_cost,
    uint64_t reproduction_minimum_body,
    uint64_t selected_count,
    compost_reproduction_assessment_t *assessment
)
{
    if (assessment == NULL || !finite(parent_reserve) || !finite(birth_cost) ||
        parent_reserve < 0.0 || birth_cost < 0.0) {
        return COMPOST_STATUS_INVALID_ARGUMENT;
    }
    assessment->score = selected_count >= 2U ? (double)selected_count : -INFINITY;
    assessment->allowed = body_size >= reproduction_minimum_body &&
        selected_count >= 2U && parent_reserve - birth_cost >= 0.0;
    assessment->selected_count = selected_count;
    assessment->parent_reserve_after_cost = parent_reserve - birth_cost;
    return finite(assessment->parent_reserve_after_cost) ? COMPOST_STATUS_OK : COMPOST_STATUS_INVALID_ARGUMENT;
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

static compost_structure_t *find_structure(
    compost_structure_t *structures,
    size_t count,
    uint8_t left,
    uint8_t right
)
{
    for (size_t index = 0U; index < count; ++index) {
        if (structures[index].occupied && structures[index].left == left &&
            structures[index].right == right) {
            return &structures[index];
        }
    }
    return NULL;
}

static compost_structure_t *free_structure(
    compost_structure_t *structures,
    size_t count
)
{
    for (size_t index = 0U; index < count; ++index) {
        if (!structures[index].occupied) {
            return &structures[index];
        }
    }
    return NULL;
}

static bool add_double(double left, double right, double *result)
{
    *result = left + right;
    return finite(*result);
}

static compost_status_t add_mass_for_structure(
    compost_body_t *body,
    double strength,
    uint64_t *created_mass
)
{
    uint64_t mass = 0U;
    if (compost_structural_mass(strength, &mass) != COMPOST_STATUS_OK ||
        !add_u64(body->structural_mass, mass, &body->structural_mass) ||
        !add_u64(body->structural_mass, UINT64_C(0), &body->structural_mass)) {
        return COMPOST_STATUS_INVALID_ARGUMENT;
    }
    *created_mass = mass;
    return COMPOST_STATUS_OK;
}

static void activate_receptor(compost_organism_t *organism, uint8_t symbol)
{
    const size_t cell = (size_t)symbol / 64U;
    const uint32_t bit = (uint32_t)symbol % 64U;
    organism->activated_receptors[cell] |= UINT64_C(1) << bit;
}

compost_status_t compost_organism_digest(
    compost_organism_t *organism,
    const compost_step_input_t *input,
    compost_step_result_t *result
)
{
    if (organism == NULL || input == NULL || result == NULL ||
        !organism->initialized || organism->status != COMPOST_LIFECYCLE_ALIVE ||
        (input->length > 0U && (input->food == NULL || input->nutrition == NULL))) {
        return COMPOST_STATUS_INVALID_ARGUMENT;
    }

    compost_organism_t next = *organism;
    compost_step_result_t next_result = {0};
    next_result.consumed_bytes = input->length;
    compost_activity_counters_t counters = {0};
    counters.bytes_eaten = (uint64_t)input->length;
    counters.processed_bytes = (uint64_t)input->length;

    for (size_t index = 0U; index < input->length; ++index) {
        const double nutrition = input->nutrition[index];
        if (!finite(nutrition)) {
            return COMPOST_STATUS_INVALID_ARGUMENT;
        }
        if (nutrition <= 0.0) {
            if (!add_u64(counters.rejected_bytes, UINT64_C(1), &counters.rejected_bytes)) {
                return COMPOST_STATUS_INVALID_ARGUMENT;
            }
            continue;
        }
        const uint8_t symbol = input->food[index];
        activate_receptor(&next, symbol);
        compost_structure_t *atom = find_structure(next.atoms, COMPOST_MAX_ATOMS, symbol, 0U);
        const double atom_gain = next.config.atom_income * nutrition;
        if (!finite(atom_gain)) {
            return COMPOST_STATUS_INVALID_ARGUMENT;
        }
        if (atom == NULL) {
            if (next.body.atom_count > 0U &&
                next.reserve < structure_maintenance(&next) + next.config.atom_maintenance) {
                uint64_t removed_mass = 0U;
                if (remove_weakest_for_capacity(&next, &removed_mass) != COMPOST_STATUS_OK) {
                    if (!add_u64(counters.rejected_bytes, UINT64_C(1), &counters.rejected_bytes)) {
                        return COMPOST_STATUS_INVALID_ARGUMENT;
                    }
                    continue;
                }
            }
            atom = free_structure(next.atoms, COMPOST_MAX_ATOMS);
            if (atom == NULL) {
                return COMPOST_STATUS_INVALID_ARGUMENT;
            }
            if (next.body.atom_count > 0U && next.reserve < next.config.atom_formation_cost) {
                if (!add_u64(counters.rejected_bytes, UINT64_C(1), &counters.rejected_bytes)) {
                    return COMPOST_STATUS_INVALID_ARGUMENT;
                }
                continue;
            }
            if (next.body.atom_count > 0U &&
                !add_double(next.reserve, -next.config.atom_formation_cost, &next.reserve)) {
                return COMPOST_STATUS_INVALID_ARGUMENT;
            }
            memset(atom, 0, sizeof(*atom));
            atom->occupied = true;
            atom->kind = COMPOST_STRUCTURE_ATOM;
            atom->left = symbol;
            atom->strength = nutrition;
            atom->maintenance = next.config.atom_maintenance;
            atom->evidence = 1.0;
            atom->income_rate = atom_gain;
            if (!add_double(next.reserve, atom_gain, &next.reserve)) {
                return COMPOST_STATUS_INVALID_ARGUMENT;
            }
            if (!add_u64(next.body.atom_count, UINT64_C(1), &next.body.atom_count)) {
                return COMPOST_STATUS_INVALID_ARGUMENT;
            }
        } else {
            if (!add_double(atom->strength, atom_gain, &atom->strength) ||
                !add_double(atom->evidence, 1.0, &atom->evidence) ||
                !add_double(atom->income_rate, atom_gain, &atom->income_rate) ||
                !add_double(next.reserve, atom_gain, &next.reserve)) {
                return COMPOST_STATUS_INVALID_ARGUMENT;
            }
        }
        if (!add_u64(next_result.assimilated_mass, UINT64_C(1), &next_result.assimilated_mass)) {
            return COMPOST_STATUS_INVALID_ARGUMENT;
        }
    }

    for (size_t index = 0U; index + 1U < input->length; ++index) {
        const double left_nutrition = input->nutrition[index];
        const double right_nutrition = input->nutrition[index + 1U];
        if (left_nutrition <= 0.0 || right_nutrition <= 0.0) {
            continue;
        }
        const uint8_t left = input->food[index];
        const uint8_t right = input->food[index + 1U];
        const double pair_nutrition = left_nutrition < right_nutrition ? left_nutrition : right_nutrition;
        compost_structure_t *composite = find_structure(next.composites, COMPOST_MAX_COMPOSITES, left, right);
        if (composite != NULL) {
            const double composite_gain = next.config.composite_income * pair_nutrition;
            uint64_t old_mass = 0U;
            uint64_t new_mass = 0U;
            if (!finite(composite_gain) ||
                compost_structural_mass(composite->strength, &old_mass) != COMPOST_STATUS_OK ||
                !add_double(composite->strength, composite_gain, &composite->strength) ||
                !add_double(composite->evidence, 1.0, &composite->evidence) ||
                !add_double(composite->income_rate, composite_gain, &composite->income_rate) ||
                !add_double(next.reserve, composite_gain, &next.reserve) ||
                compost_structural_mass(composite->strength, &new_mass) != COMPOST_STATUS_OK ||
                new_mass < old_mass ||
                !add_u64(next.body.structural_mass, new_mass - old_mass, &next.body.structural_mass) ||
                !add_u64(next.material_flow.structural_created_mass, new_mass - old_mass,
                         &next.material_flow.structural_created_mass) ||
                !add_u64(counters.composites_strengthened, UINT64_C(1), &counters.composites_strengthened)) {
                return COMPOST_STATUS_INVALID_ARGUMENT;
            }
            continue;
        }
        compost_structure_t *relation = find_structure(next.relations, COMPOST_MAX_RELATIONS, left, right);
        const double relation_gain = next.config.relation_income * pair_nutrition;
        if (!finite(relation_gain)) {
            return COMPOST_STATUS_INVALID_ARGUMENT;
        }
        if (relation == NULL) {
            if (next.body.atom_count > 0U &&
                next.reserve < structure_maintenance(&next) + next.config.relation_maintenance) {
                uint64_t removed_mass = 0U;
                if (remove_weakest_for_capacity(&next, &removed_mass) != COMPOST_STATUS_OK) {
                    continue;
                }
            }
            if (next.reserve < next.config.relation_formation_cost) {
                continue;
            }
            relation = free_structure(next.relations, COMPOST_MAX_RELATIONS);
            if (relation == NULL ||
                !add_double(next.reserve, -next.config.relation_formation_cost, &next.reserve)) {
                return COMPOST_STATUS_INVALID_ARGUMENT;
            }
            memset(relation, 0, sizeof(*relation));
            relation->occupied = true;
            relation->kind = COMPOST_STRUCTURE_RELATION;
            relation->left = left;
            relation->right = right;
            relation->strength = pair_nutrition;
            relation->maintenance = next.config.relation_maintenance;
            relation->evidence = 1.0;
            relation->income_rate = relation_gain;
            if (!add_double(next.reserve, relation_gain, &next.reserve)) {
                return COMPOST_STATUS_INVALID_ARGUMENT;
            }
            uint64_t created_mass = 0U;
            if (add_mass_for_structure(&next.body, relation->strength, &created_mass) != COMPOST_STATUS_OK ||
                next.body.structural_mass > next.config.max_body_mass ||
                !add_u64(next.body.relation_count, UINT64_C(1), &next.body.relation_count) ||
                !add_u64(next.material_flow.structural_created_mass, created_mass, &next.material_flow.structural_created_mass) ||
                !add_u64(counters.relations_created, UINT64_C(1), &counters.relations_created)) {
                return COMPOST_STATUS_INVALID_ARGUMENT;
            }
            if (!add_u64(next_result.relations_created, UINT64_C(1), &next_result.relations_created)) {
                return COMPOST_STATUS_INVALID_ARGUMENT;
            }
        } else {
            uint64_t old_mass = 0U;
            uint64_t new_mass = 0U;
            if (compost_structural_mass(relation->strength, &old_mass) != COMPOST_STATUS_OK) {
                return COMPOST_STATUS_INVALID_ARGUMENT;
            }
            if (!add_double(relation->strength, relation_gain, &relation->strength) ||
                !add_double(relation->evidence, 1.0, &relation->evidence) ||
                !add_double(relation->income_rate, relation_gain, &relation->income_rate) ||
                !add_double(next.reserve, relation_gain, &next.reserve) ||
                !add_u64(counters.relations_strengthened, UINT64_C(1), &counters.relations_strengthened)) {
                return COMPOST_STATUS_INVALID_ARGUMENT;
            }
            if (compost_structural_mass(relation->strength, &new_mass) != COMPOST_STATUS_OK ||
                new_mass < old_mass ||
                !add_u64(next.body.structural_mass, new_mass - old_mass, &next.body.structural_mass) ||
                !add_u64(next.material_flow.structural_created_mass, new_mass - old_mass,
                         &next.material_flow.structural_created_mass)) {
                return COMPOST_STATUS_INVALID_ARGUMENT;
            }
            if (!add_u64(next_result.relations_strengthened, UINT64_C(1), &next_result.relations_strengthened)) {
                return COMPOST_STATUS_INVALID_ARGUMENT;
            }
        }
    }
    counters.structural_mass_added = next.material_flow.structural_created_mass - organism->material_flow.structural_created_mass;
    next_result.rejected_mass = counters.rejected_bytes;
    if (compost_activity_ledger_add(&next.activity, &counters, next.body.structural_mass, &DEFAULT_ACTIVITY_COSTS) != COMPOST_STATUS_OK) {
        return COMPOST_STATUS_INVALID_ARGUMENT;
    }
    if (!add_u64(next.material_flow.input_mass, (uint64_t)input->length, &next.material_flow.input_mass) ||
        !add_u64(next.material_flow.processed_mass, (uint64_t)input->length, &next.material_flow.processed_mass) ||
        !add_u64(next.material_flow.assimilated_mass, next_result.assimilated_mass, &next.material_flow.assimilated_mass) ||
        !add_u64(next.material_flow.rejected_mass, counters.rejected_bytes, &next.material_flow.rejected_mass) ||
        !add_u64(next.material_flow.expelled_mass, counters.rejected_bytes, &next.material_flow.expelled_mass) ||
        !add_u64(next.material_flow.external_expelled_mass, counters.rejected_bytes,
                 &next.material_flow.external_expelled_mass) ||
        !add_u64(next.cursor, (uint64_t)input->length, &next.cursor)) {
        return COMPOST_STATUS_INVALID_ARGUMENT;
    }
    *organism = next;
    *result = next_result;
    return COMPOST_STATUS_OK;
}

compost_status_t compost_organism_enqueue_external(
    compost_organism_t *organism,
    const compost_step_input_t *input
)
{
    if (organism == NULL || input == NULL || !organism->initialized ||
        organism->status != COMPOST_LIFECYCLE_ALIVE ||
        (input->length > 0U && (input->food == NULL || input->nutrition == NULL))) {
        return COMPOST_STATUS_INVALID_ARGUMENT;
    }
    if (validate_gut(organism) != COMPOST_STATUS_OK) return COMPOST_STATUS_INVALID_STATE;
    compost_organism_t next = *organism;
    size_t offset = 0U;
    size_t required_chunks = input->length / COMPOST_MAX_GUT_CHUNK_BYTES;
    if ((input->length % COMPOST_MAX_GUT_CHUNK_BYTES) != 0U) ++required_chunks;
    if (required_chunks > (size_t)(COMPOST_MAX_GUT_CHUNKS - next.gut_count)) {
        return COMPOST_STATUS_BUFFER_TOO_SMALL;
    }
    for (size_t index = 0U; index < input->length; ++index) {
        if (!finite(input->nutrition[index])) return COMPOST_STATUS_INVALID_ARGUMENT;
    }
    if (!add_u64(next.material_flow.input_mass, (uint64_t)input->length,
                 &next.material_flow.input_mass)) {
        return COMPOST_STATUS_INVALID_ARGUMENT;
    }
    while (offset < input->length) {
        const size_t amount = (input->length - offset) < COMPOST_MAX_GUT_CHUNK_BYTES
            ? input->length - offset : COMPOST_MAX_GUT_CHUNK_BYTES;
        const uint32_t slot = (next.gut_head + next.gut_count) % COMPOST_MAX_GUT_CHUNKS;
        compost_gut_chunk_t *chunk = &next.gut[slot];
        memset(chunk, 0, sizeof(*chunk));
        chunk->mass = (uint64_t)amount;
        chunk->origin = COMPOST_MATERIAL_EXTERNAL;
        chunk->payload_length = (uint32_t)amount;
        memcpy(chunk->payload, input->food + offset, amount * sizeof(chunk->payload[0]));
        memcpy(chunk->nutrition, input->nutrition + offset, amount * sizeof(chunk->nutrition[0]));
        ++next.gut_count;
        offset += amount;
    }
    *organism = next;
    return COMPOST_STATUS_OK;
}

compost_status_t compost_organism_process_gut(
    compost_organism_t *organism,
    uint64_t capacity,
    compost_gut_process_result_t *result
)
{
    if (organism == NULL || result == NULL || !organism->initialized ||
        organism->status != COMPOST_LIFECYCLE_ALIVE) {
        return COMPOST_STATUS_INVALID_ARGUMENT;
    }
    if (validate_gut(organism) != COMPOST_STATUS_OK) return COMPOST_STATUS_INVALID_STATE;
    compost_organism_t next = *organism;
    compost_gut_process_result_t next_result = {0};
    uint64_t resorbed_processed = 0U;
    while (capacity > 0U && next.gut_count > 0U) {
        compost_gut_chunk_t *chunk = &next.gut[next.gut_head];
        if (chunk->mass == 0U ||
            (chunk->origin == COMPOST_MATERIAL_EXTERNAL &&
             (chunk->payload_length == 0U || chunk->payload_length != chunk->mass)) ||
            (chunk->origin != COMPOST_MATERIAL_EXTERNAL &&
             chunk->origin != COMPOST_MATERIAL_RESORPTION)) {
            return COMPOST_STATUS_INVALID_STATE;
        }
        const uint64_t amount = chunk->mass < capacity ? chunk->mass : capacity;
        if (chunk->origin == COMPOST_MATERIAL_EXTERNAL) {
            compost_step_input_t input = {
                chunk->payload, chunk->nutrition, (size_t)amount
            };
            compost_step_result_t digestion = {0};
            compost_status_t status = compost_organism_digest(&next, &input, &digestion);
            if (status != COMPOST_STATUS_OK || next.material_flow.input_mass < amount) {
                return status == COMPOST_STATUS_OK ? COMPOST_STATUS_INVALID_STATE : status;
            }
            next.material_flow.input_mass -= amount;
            if (!add_u64(next_result.assimilated_mass, digestion.assimilated_mass,
                         &next_result.assimilated_mass) ||
                !add_u64(next_result.rejected_mass, digestion.rejected_mass,
                         &next_result.rejected_mass) ||
                !add_u64(next_result.expelled_mass, digestion.rejected_mass,
                         &next_result.expelled_mass)) {
                return COMPOST_STATUS_INVALID_ARGUMENT;
            }
            const size_t consumed = (size_t)amount;
            const size_t remaining = (size_t)chunk->mass - consumed;
            if (remaining > 0U) {
                memmove(chunk->payload, chunk->payload + consumed, remaining * sizeof(chunk->payload[0]));
                memmove(chunk->nutrition, chunk->nutrition + consumed, remaining * sizeof(chunk->nutrition[0]));
            }
            chunk->payload_length = (uint32_t)remaining;
            chunk->mass = (uint64_t)remaining;
        } else {
            chunk->mass -= amount;
            if (!add_u64(resorbed_processed, amount, &resorbed_processed) ||
                !add_u64(next.material_flow.processed_mass, amount, &next.material_flow.processed_mass) ||
                !add_u64(next.material_flow.expelled_mass, amount, &next.material_flow.expelled_mass) ||
                !add_u64(next.material_flow.resorption_expelled_mass, amount,
                         &next.material_flow.resorption_expelled_mass) ||
                !add_u64(next_result.expelled_mass, amount, &next_result.expelled_mass)) {
                return COMPOST_STATUS_INVALID_ARGUMENT;
            }
        }
        capacity -= amount;
        if (!add_u64(next_result.processed_mass, amount, &next_result.processed_mass)) {
            return COMPOST_STATUS_INVALID_ARGUMENT;
        }
        if (chunk->mass == 0U) {
            memset(chunk, 0, sizeof(*chunk));
            next.gut_head = (next.gut_head + 1U) % COMPOST_MAX_GUT_CHUNKS;
            --next.gut_count;
        }
    }
    if (resorbed_processed > 0U) {
        compost_activity_counters_t counters = {0};
        counters.resorbed_processed_bytes = resorbed_processed;
        if (compost_activity_ledger_add(&next.activity, &counters, next.body.structural_mass,
                                        &DEFAULT_ACTIVITY_COSTS) != COMPOST_STATUS_OK) {
            return COMPOST_STATUS_INVALID_ARGUMENT;
        }
    }
    if (settle_activity_debt(&next) != COMPOST_STATUS_OK) {
        return COMPOST_STATUS_INVALID_ARGUMENT;
    }
    *organism = next;
    *result = next_result;
    return COMPOST_STATUS_OK;
}

compost_status_t compost_organism_step(
    compost_organism_t *organism,
    const compost_step_input_t *input,
    compost_cycle_result_t *result
)
{
    if (organism == NULL || input == NULL || result == NULL || !organism->initialized ||
        (input->length > 0U && (input->food == NULL || input->nutrition == NULL))) {
        return COMPOST_STATUS_INVALID_ARGUMENT;
    }
    if (organism->status == COMPOST_LIFECYCLE_DEAD) {
        *result = (compost_cycle_result_t){0};
        result->status_after = COMPOST_LIFECYCLE_DEAD;
        return COMPOST_STATUS_OK;
    }
    compost_organism_t next = *organism;
    compost_cycle_result_t next_result = {0};
    compost_status_t status = compost_organism_digest(&next, input, &next_result.digestion);
    if (status != COMPOST_STATUS_OK) {
        return status;
    }
    const uint64_t lifecycle_mass_before = next.body.structural_mass;
    const uint64_t lifecycle_resorptions_before = next.activity.counters.resorption_events;
    status = compost_organism_consolidate(
        &next,
        next.config.composite_maintenance,
        next.config.consolidation_formation_cost,
        &next_result.composites_consolidated
    );
    if (status != COMPOST_STATUS_OK) {
        return status;
    }
    status = compost_organism_maintenance(&next, &next_result.maintenance);
    if (status != COMPOST_STATUS_OK) {
        return status;
    }
    compost_activity_counters_t lifecycle_counters = {0};
    lifecycle_counters.composites_created = next_result.composites_consolidated;
    if (next.body.structural_mass >= lifecycle_mass_before) {
        lifecycle_counters.structural_mass_added = next.body.structural_mass - lifecycle_mass_before;
    } else {
        lifecycle_counters.structural_mass_lost = lifecycle_mass_before - next.body.structural_mass;
    }
    if (next.activity.counters.resorption_events >= lifecycle_resorptions_before) {
        lifecycle_counters.resorption_events =
            next.activity.counters.resorption_events - lifecycle_resorptions_before;
    }
    status = activity_charge_only(&next.activity, &lifecycle_counters, &DEFAULT_ACTIVITY_COSTS);
    if (status != COMPOST_STATUS_OK) {
        return status;
    }
    next_result.status_after = next.status;
    *organism = next;
    *result = next_result;
    return COMPOST_STATUS_OK;
}

static uint64_t structure_count(const compost_organism_t *organism)
{
    return organism->body.atom_count + organism->body.relation_count + organism->body.composite_count;
}

static compost_status_t append_resorption_chunk(compost_organism_t *organism, uint64_t mass)
{
    if (mass == 0U) return COMPOST_STATUS_OK;
    if (organism->gut_count >= COMPOST_MAX_GUT_CHUNKS) return COMPOST_STATUS_INVALID_STATE;
    const uint32_t slot = (organism->gut_head + organism->gut_count) % COMPOST_MAX_GUT_CHUNKS;
    memset(&organism->gut[slot], 0, sizeof(organism->gut[slot]));
    organism->gut[slot].mass = mass;
    organism->gut[slot].origin = COMPOST_MATERIAL_RESORPTION;
    organism->gut_count += 1U;
    return COMPOST_STATUS_OK;
}

static double structure_maintenance(const compost_organism_t *organism)
{
    double total = 0.0;
    for (size_t index = 0U; index < COMPOST_MAX_ATOMS; ++index) {
        if (organism->atoms[index].occupied) {
            total += organism->atoms[index].maintenance;
        }
    }
    for (size_t index = 0U; index < COMPOST_MAX_RELATIONS; ++index) {
        if (organism->relations[index].occupied) {
            total += organism->relations[index].maintenance;
        }
    }
    for (size_t index = 0U; index < COMPOST_MAX_COMPOSITES; ++index) {
        if (organism->composites[index].occupied) {
            total += organism->composites[index].maintenance;
        }
    }
    return total;
}

static compost_status_t lifecycle_weaken_member(
    compost_organism_t *organism,
    uint64_t *resorbed_mass,
    bool *weakened,
    bool *detached
)
{
    bool present[COMPOST_MAX_ATOMS] = {false};
    bool weighted[COMPOST_MAX_ATOMS] = {false};
    double weight[COMPOST_MAX_ATOMS] = {0.0};
    for (size_t index = 0U; index < COMPOST_MAX_ATOMS; ++index) {
        if (organism->atoms[index].occupied) present[organism->atoms[index].left] = true;
    }
    for (size_t collection = 0U; collection < 2U; ++collection) {
        const compost_structure_t *structures = collection == 0U
            ? organism->relations : organism->composites;
        const size_t count = collection == 0U ? COMPOST_MAX_RELATIONS : COMPOST_MAX_COMPOSITES;
        for (size_t index = 0U; index < count; ++index) {
            const compost_structure_t *structure = &structures[index];
            if (!structure->occupied) continue;
            present[structure->left] = true;
            present[structure->right] = true;
            if (!weighted[structure->left] || structure->strength < weight[structure->left]) {
                weighted[structure->left] = true;
                weight[structure->left] = structure->strength;
            }
            if (!weighted[structure->right] || structure->strength < weight[structure->right]) {
                weighted[structure->right] = true;
                weight[structure->right] = structure->strength;
            }
        }
    }
    bool member_found = false;
    uint8_t member = 0U;
    double member_weight = 0.0;
    for (size_t index = 0U; index < COMPOST_MAX_ATOMS; ++index) {
        if (!present[index]) continue;
        const double candidate_weight = weighted[index] ? weight[index] : 0.0;
        if (!member_found || candidate_weight < member_weight) {
            member_found = true;
            member = (uint8_t)index;
            member_weight = candidate_weight;
        }
    }
    if (!member_found) return COMPOST_STATUS_OK;

    compost_structure_t *atom = NULL;
    for (size_t index = 0U; index < COMPOST_MAX_ATOMS; ++index) {
        if (organism->atoms[index].occupied && organism->atoms[index].left == member) {
            atom = &organism->atoms[index];
            break;
        }
    }
    if (atom != NULL && atom->strength > 1.0) {
        atom->strength -= 1.0;
        *weakened = true;
        return COMPOST_STATUS_OK;
    }

    if (atom != NULL) {
        for (size_t collection = 0U; collection < 2U; ++collection) {
            compost_structure_t *structures = collection == 0U
                ? organism->relations : organism->composites;
            const size_t count = collection == 0U ? COMPOST_MAX_RELATIONS : COMPOST_MAX_COMPOSITES;
            for (size_t index = 0U; index < count; ++index) {
                compost_structure_t *structure = &structures[index];
                if (structure->occupied &&
                    (structure->left == member || structure->right == member) &&
                    remove_structure_entry(organism, structure, resorbed_mass) != COMPOST_STATUS_OK) {
                    return COMPOST_STATUS_INVALID_STATE;
                }
            }
        }
        if (remove_structure_entry(organism, atom, resorbed_mass) != COMPOST_STATUS_OK) {
            return COMPOST_STATUS_INVALID_STATE;
        }
        *detached = true;
        return COMPOST_STATUS_OK;
    }

    compost_structure_t *target = NULL;
    int target_kind = 0;
    for (size_t collection = 0U; collection < 2U; ++collection) {
        compost_structure_t *structures = collection == 0U
            ? organism->relations : organism->composites;
        const size_t count = collection == 0U ? COMPOST_MAX_RELATIONS : COMPOST_MAX_COMPOSITES;
        const int kind = collection == 0U ? 1 : 0;
        for (size_t index = 0U; index < count; ++index) {
            compost_structure_t *candidate = &structures[index];
            if (!candidate->occupied ||
                (candidate->left != member && candidate->right != member)) continue;
            if (target == NULL || candidate->strength < target->strength ||
                (candidate->strength == target->strength && kind < target_kind) ||
                (candidate->strength == target->strength && kind == target_kind &&
                 (candidate->left < target->left ||
                  (candidate->left == target->left && candidate->right < target->right)))) {
                target = candidate;
                target_kind = kind;
            }
        }
    }
    if (target == NULL) return COMPOST_STATUS_OK;
    if (target->strength > 1.0) {
        uint64_t before = 0U;
        uint64_t after = 0U;
        if (compost_structural_mass(target->strength, &before) != COMPOST_STATUS_OK ||
            compost_structural_mass(target->strength - 1.0, &after) != COMPOST_STATUS_OK ||
            before < after || organism->body.structural_mass < before - after) {
            return COMPOST_STATUS_INVALID_STATE;
        }
        target->strength -= 1.0;
        if (before > after) {
            const uint64_t lost = before - after;
            if (compost_organism_enqueue_resorbed(organism, lost) != COMPOST_STATUS_OK ||
                !add_u64(*resorbed_mass, lost, resorbed_mass)) {
                return COMPOST_STATUS_INVALID_STATE;
            }
            organism->body.structural_mass -= lost;
        }
        *weakened = true;
        return COMPOST_STATUS_OK;
    }

    for (size_t collection = 0U; collection < 2U; ++collection) {
        compost_structure_t *structures = collection == 0U
            ? organism->relations : organism->composites;
        const size_t count = collection == 0U ? COMPOST_MAX_RELATIONS : COMPOST_MAX_COMPOSITES;
        for (size_t index = 0U; index < count; ++index) {
            compost_structure_t *structure = &structures[index];
            if (structure->occupied &&
                (structure->left == member || structure->right == member) &&
                remove_structure_entry(organism, structure, resorbed_mass) != COMPOST_STATUS_OK) {
                return COMPOST_STATUS_INVALID_STATE;
            }
        }
    }
    *detached = true;
    return COMPOST_STATUS_OK;
}

static compost_status_t lifecycle_maintenance(
    compost_organism_t *organism,
    compost_maintenance_result_t *result
)
{
    compost_maintenance_result_t next_result = {0};
    next_result.required = structure_maintenance(organism);
    if (!finite(next_result.required)) return COMPOST_STATUS_INVALID_ARGUMENT;
    next_result.paid = organism->reserve < next_result.required
        ? organism->reserve : next_result.required;
    next_result.deficit = next_result.required - next_result.paid;
    organism->reserve -= next_result.paid;
    uint64_t budget = 0U;
    if (compost_maintenance_weakening_budget(
            next_result.deficit, organism->body.structural_mass, &budget) != COMPOST_STATUS_OK) {
        return COMPOST_STATUS_INVALID_ARGUMENT;
    }
    for (uint64_t index = 0U; index < budget; ++index) {
        bool weakened = false;
        bool detached = false;
        uint64_t resorbed = 0U;
        if (lifecycle_weaken_member(organism, &resorbed, &weakened, &detached) != COMPOST_STATUS_OK) {
            return COMPOST_STATUS_INVALID_STATE;
        }
        if (!weakened && !detached) break;
        if (weakened && !add_u64(next_result.weakened_candidates, UINT64_C(1),
                                 &next_result.weakened_candidates)) {
            return COMPOST_STATUS_INVALID_ARGUMENT;
        }
        if (!add_u64(next_result.resorbed_mass, resorbed, &next_result.resorbed_mass)) {
            return COMPOST_STATUS_INVALID_ARGUMENT;
        }
    }
    if (organism->age_in_cycles == UINT64_MAX) return COMPOST_STATUS_INVALID_ARGUMENT;
    organism->age_in_cycles += UINT64_C(1);
    if (structure_count(organism) == 0U) {
        organism->status = COMPOST_LIFECYCLE_DEAD;
        organism->territory.alive = false;
    }
    *result = next_result;
    return COMPOST_STATUS_OK;
}

static compost_status_t forget_structure(
    compost_organism_t *organism,
    compost_structure_t *structure,
    uint64_t *resorbed_mass
)
{
    const bool material = structure->kind != COMPOST_STRUCTURE_ATOM;
    uint64_t before = 0U;
    uint64_t after = 0U;
    if (material && compost_structural_mass(structure->strength, &before) != COMPOST_STATUS_OK) {
        return COMPOST_STATUS_INVALID_ARGUMENT;
    }
    compost_forgetting_delta_t delta = {0};
    if (compost_forgetting_delta(
            structure->strength, structure->income_rate, structure->maintenance,
            organism->config.income_decay, &delta) != COMPOST_STATUS_OK) {
        return COMPOST_STATUS_INVALID_ARGUMENT;
    }
    if (material && compost_structural_mass(delta.strength_after, &after) != COMPOST_STATUS_OK) {
        return COMPOST_STATUS_INVALID_ARGUMENT;
    }
    if (after > before) {
        const uint64_t increase = after - before;
        if (!add_u64(organism->body.structural_mass, increase, &organism->body.structural_mass)) {
            return COMPOST_STATUS_INVALID_ARGUMENT;
        }
    } else if (before > after) {
        const uint64_t decrease = before - after;
        if (organism->body.structural_mass < decrease) {
            return COMPOST_STATUS_INVALID_STATE;
        }
        organism->body.structural_mass -= decrease;
        if (!add_u64(*resorbed_mass, decrease, resorbed_mass) ||
            !add_u64(organism->material_flow.resorbed_mass, decrease, &organism->material_flow.resorbed_mass)) {
            return COMPOST_STATUS_INVALID_ARGUMENT;
        }
    }
    structure->strength = delta.strength_after;
    structure->income_rate = delta.income_rate_after;
    return COMPOST_STATUS_OK;
}

compost_status_t compost_organism_maintenance(
    compost_organism_t *organism,
    compost_maintenance_result_t *result
)
{
    if (organism == NULL || result == NULL || !organism->initialized ||
        organism->status != COMPOST_LIFECYCLE_ALIVE) {
        return COMPOST_STATUS_INVALID_ARGUMENT;
    }
    compost_organism_t next = *organism;
    compost_maintenance_result_t next_result = {0};
    uint64_t forgotten_mass = 0U;
    next_result.required = structure_maintenance(&next);
    if (!finite(next_result.required)) {
        return COMPOST_STATUS_INVALID_ARGUMENT;
    }
    next_result.paid = next.reserve < next_result.required ? next.reserve : next_result.required;
    next_result.deficit = next_result.required - next_result.paid;
    next.reserve -= next_result.paid;
    for (size_t index = 0U; index < COMPOST_MAX_ATOMS; ++index) {
        if (next.atoms[index].occupied && forget_structure(&next, &next.atoms[index], &forgotten_mass) != COMPOST_STATUS_OK) {
            return COMPOST_STATUS_INVALID_ARGUMENT;
        }
    }
    for (size_t index = 0U; index < COMPOST_MAX_RELATIONS; ++index) {
        if (next.relations[index].occupied && forget_structure(&next, &next.relations[index], &forgotten_mass) != COMPOST_STATUS_OK) {
            return COMPOST_STATUS_INVALID_ARGUMENT;
        }
    }
    for (size_t index = 0U; index < COMPOST_MAX_COMPOSITES; ++index) {
        if (next.composites[index].occupied && forget_structure(&next, &next.composites[index], &forgotten_mass) != COMPOST_STATUS_OK) {
            return COMPOST_STATUS_INVALID_ARGUMENT;
        }
    }
    while (structure_count(&next) > 0U && next.reserve < structure_maintenance(&next)) {
        uint64_t removed_mass = 0U;
        if (remove_weakest_for_pressure(&next, &removed_mass) != COMPOST_STATUS_OK) {
            return COMPOST_STATUS_INVALID_STATE;
        }
        if (!add_u64(next_result.weakened_candidates, UINT64_C(1), &next_result.weakened_candidates) ||
            !add_u64(next_result.resorbed_mass, removed_mass, &next_result.resorbed_mass) ||
            !add_u64(next.activity.counters.resorption_events, UINT64_C(1),
                     &next.activity.counters.resorption_events) ||
            !add_u64(next.activity.counters.structural_mass_lost, removed_mass,
                     &next.activity.counters.structural_mass_lost)) {
            return COMPOST_STATUS_INVALID_ARGUMENT;
        }
    }
    if (!add_u64(next_result.resorbed_mass, forgotten_mass, &next_result.resorbed_mass) ||
        !add_u64(next.activity.counters.structural_mass_lost, forgotten_mass,
                 &next.activity.counters.structural_mass_lost) ||
        append_resorption_chunk(&next, forgotten_mass) != COMPOST_STATUS_OK) {
        return COMPOST_STATUS_INVALID_STATE;
    }
    if (next.age_in_cycles == UINT64_MAX) {
        return COMPOST_STATUS_INVALID_ARGUMENT;
    }
    next.age_in_cycles += UINT64_C(1);
    if (structure_count(&next) == 0U) {
        next.status = COMPOST_LIFECYCLE_DEAD;
        next.territory.alive = false;
    }
    *organism = next;
    *result = next_result;
    return COMPOST_STATUS_OK;
}

compost_status_t compost_organism_consolidate(
    compost_organism_t *organism,
    double composite_maintenance,
    double consolidation_formation_cost,
    uint64_t *consolidated_count
)
{
    if (organism == NULL || consolidated_count == NULL || !organism->initialized ||
        !finite(composite_maintenance) || composite_maintenance <= 0.0 ||
        !finite(consolidation_formation_cost) || consolidation_formation_cost < 0.0) {
        return COMPOST_STATUS_INVALID_ARGUMENT;
    }
    compost_organism_t next = *organism;
    uint64_t total = 0U;
    for (;;) {
        compost_structure_t *candidate = NULL;
        for (size_t index = 0U; index < COMPOST_MAX_RELATIONS; ++index) {
            compost_structure_t *relation = &next.relations[index];
            if (!relation->occupied) continue;
            const double evidence_scale = relation->evidence > 1.0 ? relation->evidence : 1.0;
            const double before = relation->maintenance * evidence_scale;
            const double after = composite_maintenance * evidence_scale;
            const double useful_evidence = relation->evidence * (relation->strength / evidence_scale);
            if (!finite(before) || !finite(after) || !finite(useful_evidence) ||
                !(after + consolidation_formation_cost < before) ||
                !(useful_evidence > consolidation_formation_cost)) continue;
            if (candidate == NULL || relation->left < candidate->left ||
                (relation->left == candidate->left && relation->right < candidate->right)) {
                candidate = relation;
            }
        }
        if (candidate == NULL) break;
        compost_structure_t *composite = free_structure(next.composites, COMPOST_MAX_COMPOSITES);
        if (composite == NULL) return COMPOST_STATUS_INVALID_STATE;
        uint64_t relation_mass = 0U;
        uint64_t composite_mass = 0U;
        if (compost_structural_mass(candidate->strength, &relation_mass) != COMPOST_STATUS_OK) {
            return COMPOST_STATUS_INVALID_STATE;
        }
        *composite = *candidate;
        composite->kind = COMPOST_STRUCTURE_COMPOSITE;
        composite->maintenance = composite_maintenance;
        if (compost_structural_mass(composite->strength, &composite_mass) != COMPOST_STATUS_OK) {
            return COMPOST_STATUS_INVALID_STATE;
        }
        memset(candidate, 0, sizeof(*candidate));
        if (next.body.relation_count == 0U) return COMPOST_STATUS_INVALID_STATE;
        --next.body.relation_count;
        ++next.body.composite_count;
        if (composite_mass > relation_mass) {
            const uint64_t increase = composite_mass - relation_mass;
            if (!add_u64(next.body.structural_mass, increase, &next.body.structural_mass) ||
                !add_u64(next.material_flow.structural_created_mass, increase,
                         &next.material_flow.structural_created_mass)) {
                return COMPOST_STATUS_INVALID_ARGUMENT;
            }
        } else if (relation_mass > composite_mass) {
            const uint64_t decrease = relation_mass - composite_mass;
            if (next.body.structural_mass < decrease ||
                append_resorption_chunk(&next, decrease) != COMPOST_STATUS_OK ||
                !add_u64(next.material_flow.resorbed_mass, decrease, &next.material_flow.resorbed_mass)) {
                return COMPOST_STATUS_INVALID_STATE;
            }
            next.body.structural_mass -= decrease;
        }
        if (!add_u64(next.activity.counters.composites_created, UINT64_C(1),
                     &next.activity.counters.composites_created) ||
            !add_u64(total, UINT64_C(1), &total)) {
            return COMPOST_STATUS_INVALID_ARGUMENT;
        }
    }
    *organism = next;
    *consolidated_count = total;
    return COMPOST_STATUS_OK;
}

compost_status_t compost_organism_enqueue_resorbed(
    compost_organism_t *organism,
    uint64_t mass
)
{
    if (organism == NULL || !organism->initialized || mass == 0U) {
        return COMPOST_STATUS_INVALID_ARGUMENT;
    }
    if (validate_gut(organism) != COMPOST_STATUS_OK) return COMPOST_STATUS_INVALID_STATE;
    if (append_resorption_chunk(organism, mass) != COMPOST_STATUS_OK) {
        return COMPOST_STATUS_INVALID_STATE;
    }
    if (!add_u64(organism->material_flow.resorbed_mass, mass, &organism->material_flow.resorbed_mass)) {
        organism->gut_count -= 1U;
        const uint32_t slot = (organism->gut_head + organism->gut_count) % COMPOST_MAX_GUT_CHUNKS;
        organism->gut[slot].mass = 0U;
        return COMPOST_STATUS_INVALID_ARGUMENT;
    }
    return COMPOST_STATUS_OK;
}

compost_status_t compost_organism_process_resorption(
    compost_organism_t *organism,
    uint64_t capacity,
    uint64_t *processed
)
{
    if (organism == NULL || processed == NULL || !organism->initialized) {
        return COMPOST_STATUS_INVALID_ARGUMENT;
    }
    if (validate_gut(organism) != COMPOST_STATUS_OK) return COMPOST_STATUS_INVALID_STATE;
    compost_organism_t next = *organism;
    uint64_t total = 0U;
    while (capacity > 0U && next.gut_count > 0U) {
        compost_gut_chunk_t *chunk = &next.gut[next.gut_head];
        if (chunk->origin != COMPOST_MATERIAL_RESORPTION || chunk->mass == 0U) {
            return COMPOST_STATUS_INVALID_STATE;
        }
        const uint64_t amount = chunk->mass < capacity ? chunk->mass : capacity;
        chunk->mass -= amount;
        capacity -= amount;
        if (!add_u64(total, amount, &total) ||
            !add_u64(next.material_flow.processed_mass, amount, &next.material_flow.processed_mass) ||
            !add_u64(next.material_flow.expelled_mass, amount, &next.material_flow.expelled_mass) ||
            !add_u64(next.material_flow.resorption_expelled_mass, amount, &next.material_flow.resorption_expelled_mass)) {
            return COMPOST_STATUS_INVALID_ARGUMENT;
        }
        if (chunk->mass == 0U) {
            next.gut_head = (next.gut_head + 1U) % COMPOST_MAX_GUT_CHUNKS;
            next.gut_count -= 1U;
        }
    }
    if (total > 0U) {
        compost_activity_counters_t counters = {0};
        counters.resorbed_processed_bytes = total;
        if (compost_activity_ledger_add(&next.activity, &counters, next.body.structural_mass,
                                        &DEFAULT_ACTIVITY_COSTS) != COMPOST_STATUS_OK) {
            return COMPOST_STATUS_INVALID_ARGUMENT;
        }
    }
    *organism = next;
    *processed = total;
    return COMPOST_STATUS_OK;
}

compost_status_t compost_organism_verify_material_conservation(
    const compost_organism_t *organism
)
{
    if (organism == NULL || !organism->initialized || organism->body.structural_mass < UINT64_C(256)) {
        return COMPOST_STATUS_INVALID_ARGUMENT;
    }
    uint64_t external_gut = 0U;
    uint64_t resorption_gut = 0U;
    for (size_t index = 0U; index < COMPOST_MAX_GUT_CHUNKS; ++index) {
        const compost_gut_chunk_t *chunk = &organism->gut[index];
        if (chunk->origin == COMPOST_MATERIAL_EXTERNAL) {
            if (!add_u64(external_gut, chunk->mass, &external_gut)) return COMPOST_STATUS_INVALID_STATE;
        } else if (chunk->origin == COMPOST_MATERIAL_RESORPTION) {
            if (!add_u64(resorption_gut, chunk->mass, &resorption_gut)) return COMPOST_STATUS_INVALID_STATE;
        } else {
            return COMPOST_STATUS_INVALID_STATE;
        }
    }
    uint64_t external_accounted = 0U;
    if (!add_u64(organism->material_flow.assimilated_mass, organism->material_flow.external_expelled_mass,
                 &external_accounted) ||
        !add_u64(external_accounted, external_gut, &external_accounted) ||
        external_accounted != organism->material_flow.input_mass ||
        organism->material_flow.rejected_mass != organism->material_flow.external_expelled_mass) {
        return COMPOST_STATUS_INVALID_STATE;
    }
    uint64_t resorption_accounted = 0U;
    if (!add_u64(organism->material_flow.resorption_expelled_mass, resorption_gut, &resorption_accounted) ||
        resorption_accounted != organism->material_flow.resorbed_mass) {
        return COMPOST_STATUS_INVALID_STATE;
    }
    const uint64_t dynamic_mass = organism->body.structural_mass - UINT64_C(256);
    uint64_t created = 0U;
    uint64_t accounted = 0U;
    if (!add_u64(organism->material_flow.structural_created_mass,
                 organism->material_flow.structural_transferred_in, &created) ||
        !add_u64(dynamic_mass, organism->material_flow.resorbed_mass, &accounted) ||
        !add_u64(accounted, organism->material_flow.structural_transferred_out, &accounted) ||
        created != accounted) {
        return COMPOST_STATUS_INVALID_STATE;
    }
    return COMPOST_STATUS_OK;
}

static bool key_in_region(const bool selected[COMPOST_MAX_ATOMS], uint8_t key)
{
    return selected[(size_t)key];
}

static compost_status_t remove_structure_entry(
    compost_organism_t *organism,
    compost_structure_t *structure,
    uint64_t *resorbed_mass
);

static compost_status_t partition_mass(
    const compost_organism_t *parent,
    const bool selected[COMPOST_MAX_ATOMS],
    uint64_t *moved_mass,
    uint64_t *cross_mass,
    uint64_t *cross_count
)
{
    *moved_mass = 0U;
    *cross_mass = 0U;
    *cross_count = 0U;
    for (size_t collection = 0U; collection < 2U; ++collection) {
        const compost_structure_t *structures = collection == 0U ? parent->relations : parent->composites;
        const size_t count = collection == 0U ? COMPOST_MAX_RELATIONS : COMPOST_MAX_COMPOSITES;
        for (size_t index = 0U; index < count; ++index) {
            const compost_structure_t *structure = &structures[index];
            if (!structure->occupied) continue;
            const bool left_selected = key_in_region(selected, structure->left);
            const bool right_selected = key_in_region(selected, structure->right);
            uint64_t mass = 0U;
            if (compost_structural_mass(structure->strength, &mass) != COMPOST_STATUS_OK) {
                return COMPOST_STATUS_INVALID_STATE;
            }
            if (left_selected && right_selected) {
                if (!add_u64(*moved_mass, mass, moved_mass)) return COMPOST_STATUS_INVALID_STATE;
            } else if (left_selected != right_selected) {
                if (!add_u64(*cross_mass, mass, cross_mass) ||
                    !add_u64(*cross_count, UINT64_C(1), cross_count)) return COMPOST_STATUS_INVALID_STATE;
            }
        }
    }
    return COMPOST_STATUS_OK;
}

static bool boundary_matches(uint8_t left, uint8_t right, uint8_t boundary_left, uint8_t boundary_right)
{
    return (left == boundary_left && right == boundary_right) ||
           (left == boundary_right && right == boundary_left);
}

static const compost_structure_t *atom_for_key(const compost_organism_t *organism, uint8_t key)
{
    for (size_t index = 0U; index < COMPOST_MAX_ATOMS; ++index) {
        const compost_structure_t *atom = &organism->atoms[index];
        if (atom->occupied && atom->left == key) return atom;
    }
    return NULL;
}

static compost_status_t label_components(
    const compost_organism_t *organism,
    bool skip_boundary,
    uint8_t boundary_left,
    uint8_t boundary_right,
    uint8_t labels[COMPOST_MAX_ATOMS],
    uint8_t *component_count
)
{
    for (size_t index = 0U; index < COMPOST_MAX_ATOMS; ++index) labels[index] = UINT8_MAX;
    uint8_t count = 0U;
    for (size_t seed = 0U; seed < COMPOST_MAX_ATOMS; ++seed) {
        if (atom_for_key(organism, (uint8_t)seed) == NULL || labels[seed] != UINT8_MAX) continue;
        if (count == UINT8_MAX) return COMPOST_STATUS_INVALID_STATE;
        uint8_t queue[COMPOST_MAX_ATOMS] = {0};
        size_t head = 0U;
        size_t tail = 1U;
        queue[0] = (uint8_t)seed;
        labels[seed] = count;
        while (head < tail) {
            const uint8_t current = queue[head++];
            for (size_t collection = 0U; collection < 2U; ++collection) {
                const compost_structure_t *structures = collection == 0U ? organism->relations : organism->composites;
                const size_t structure_count = collection == 0U ? COMPOST_MAX_RELATIONS : COMPOST_MAX_COMPOSITES;
                for (size_t index = 0U; index < structure_count; ++index) {
                    const compost_structure_t *structure = &structures[index];
                    if (!structure->occupied || structure->left == structure->right ||
                        (skip_boundary && boundary_matches(structure->left, structure->right, boundary_left, boundary_right)) ||
                        (structure->left != current && structure->right != current)) continue;
                    const uint8_t neighbour = structure->left == current ? structure->right : structure->left;
                    if (atom_for_key(organism, neighbour) == NULL || labels[(size_t)neighbour] != UINT8_MAX) continue;
                    if (tail >= COMPOST_MAX_ATOMS) return COMPOST_STATUS_INVALID_STATE;
                    labels[(size_t)neighbour] = count;
                    queue[tail++] = neighbour;
                }
            }
        }
        ++count;
    }
    *component_count = count;
    return COMPOST_STATUS_OK;
}

static compost_status_t critical_bridge(
    const compost_organism_t *organism,
    const compost_structure_t *edge,
    bool *critical
)
{
    *critical = false;
    if (edge->kind == COMPOST_STRUCTURE_ATOM || edge->left == edge->right) return COMPOST_STATUS_OK;
    uint8_t baseline[COMPOST_MAX_ATOMS] = {0};
    uint8_t without[COMPOST_MAX_ATOMS] = {0};
    uint8_t baseline_count = 0U;
    uint8_t without_count = 0U;
    if (label_components(organism, false, 0U, 0U, baseline, &baseline_count) != COMPOST_STATUS_OK ||
        label_components(organism, true, edge->left, edge->right, without, &without_count) != COMPOST_STATUS_OK) {
        return COMPOST_STATUS_INVALID_STATE;
    }
    if (baseline_count != 1U || without_count <= baseline_count) return COMPOST_STATUS_OK;
    for (uint8_t component = 0U; component < without_count; ++component) {
        double strength = 0.0;
        for (size_t index = 0U; index < COMPOST_MAX_ATOMS; ++index) {
            if (without[index] == component) {
                const compost_structure_t *atom = atom_for_key(organism, (uint8_t)index);
                if (atom != NULL) strength += atom->strength;
            }
        }
        if (!(strength > edge->strength)) return COMPOST_STATUS_OK;
    }
    *critical = true;
    return COMPOST_STATUS_OK;
}

static compost_status_t remove_weakest_for_capacity(
    compost_organism_t *organism,
    uint64_t *resorbed_mass
)
{
    compost_structure_t *best = NULL;
    for (size_t index = 0U; index < COMPOST_MAX_ATOMS; ++index) {
        compost_structure_t *candidate = &organism->atoms[index];
        if (!candidate->occupied) continue;
        bool supported = false;
        for (size_t collection = 0U; collection < 2U && !supported; ++collection) {
            const compost_structure_t *structures = collection == 0U ? organism->relations : organism->composites;
            const size_t count = collection == 0U ? COMPOST_MAX_RELATIONS : COMPOST_MAX_COMPOSITES;
            for (size_t edge_index = 0U; edge_index < count; ++edge_index) {
                const compost_structure_t *edge = &structures[edge_index];
                if (edge->occupied && (edge->left == candidate->left || edge->right == candidate->left)) {
                    supported = true;
                    break;
                }
            }
        }
        if (!supported && weaker(candidate, best)) best = candidate;
    }
    for (size_t collection = 0U; collection < 2U; ++collection) {
        compost_structure_t *structures = collection == 0U ? organism->composites : organism->relations;
        const size_t count = collection == 0U ? COMPOST_MAX_COMPOSITES : COMPOST_MAX_RELATIONS;
        for (size_t index = 0U; index < count; ++index) {
            compost_structure_t *candidate = &structures[index];
            bool critical = false;
            /* Preserve an isolated atom selected by the Python-compatible
             * candidate ordering; later relation candidates must not replace
             * it during this single pressure transaction. */
            if (best != NULL && best->kind == COMPOST_STRUCTURE_ATOM) continue;
            if (!candidate->occupied ||
                critical_bridge(organism, candidate, &critical) != COMPOST_STATUS_OK || critical) continue;
            if (weaker(candidate, best)) best = candidate;
        }
    }
    if (best == NULL) return COMPOST_STATUS_INVALID_STATE;
    const compost_structure_kind_t kind = best->kind;
    const uint8_t symbol = best->left;
    if (kind == COMPOST_STRUCTURE_ATOM) {
        for (size_t index = 0U; index < COMPOST_MAX_RELATIONS; ++index) {
            compost_structure_t *edge = &organism->relations[index];
            if (edge->occupied && (edge->left == symbol || edge->right == symbol) &&
                remove_structure_entry(organism, edge, resorbed_mass) != COMPOST_STATUS_OK) {
                return COMPOST_STATUS_INVALID_STATE;
            }
        }
        for (size_t index = 0U; index < COMPOST_MAX_COMPOSITES; ++index) {
            compost_structure_t *edge = &organism->composites[index];
            if (edge->occupied && (edge->left == symbol || edge->right == symbol) &&
                remove_structure_entry(organism, edge, resorbed_mass) != COMPOST_STATUS_OK) {
                return COMPOST_STATUS_INVALID_STATE;
            }
        }
    }
    return remove_structure_entry(organism, best, resorbed_mass);
}

compost_status_t compost_organism_select_partition(
    const compost_organism_t *organism,
    double boundary_ratio_limit,
    uint8_t *child_atoms,
    size_t child_atom_capacity,
    size_t *child_atom_count,
    double *selected_ratio
)
{
    if (organism == NULL || child_atoms == NULL || child_atom_count == NULL || selected_ratio == NULL ||
        !organism->initialized || !finite(boundary_ratio_limit) ||
        !(boundary_ratio_limit > 0.0 && boundary_ratio_limit < 1.0)) {
        return COMPOST_STATUS_INVALID_ARGUMENT;
    }
    *child_atom_count = 0U;
    *selected_ratio = 0.0;
    uint8_t baseline_labels[COMPOST_MAX_ATOMS] = {0};
    uint8_t baseline_count = 0U;
    if (organism->body.atom_count < 2U ||
        label_components(organism, false, 0U, 0U, baseline_labels, &baseline_count) != COMPOST_STATUS_OK ||
        baseline_count != 1U) {
        return COMPOST_STATUS_INVALID_STATE;
    }
    bool seen[COMPOST_MAX_ATOMS][COMPOST_MAX_ATOMS] = {{false}};
    bool best_selected[COMPOST_MAX_ATOMS] = {false};
    bool found = false;
    double best_ratio = INFINITY;
    uint8_t best_left = UINT8_MAX;
    uint8_t best_right = UINT8_MAX;
    for (size_t collection = 0U; collection < 2U; ++collection) {
        const compost_structure_t *structures = collection == 0U ? organism->relations : organism->composites;
        const size_t structure_count = collection == 0U ? COMPOST_MAX_RELATIONS : COMPOST_MAX_COMPOSITES;
        for (size_t index = 0U; index < structure_count; ++index) {
            const compost_structure_t *edge = &structures[index];
            if (!edge->occupied || edge->left == edge->right ||
                atom_for_key(organism, edge->left) == NULL || atom_for_key(organism, edge->right) == NULL) continue;
            uint8_t left = edge->left;
            uint8_t right = edge->right;
            if (left > right) {
                const uint8_t swap = left;
                left = right;
                right = swap;
            }
            if (seen[(size_t)left][(size_t)right]) continue;
            seen[(size_t)left][(size_t)right] = true;
            uint8_t labels[COMPOST_MAX_ATOMS] = {0};
            uint8_t component_count = 0U;
            if (label_components(organism, true, left, right, labels, &component_count) != COMPOST_STATUS_OK || component_count != 2U) continue;
            size_t sizes[2] = {0U, 0U};
            uint8_t first[2] = {UINT8_MAX, UINT8_MAX};
            for (size_t atom = 0U; atom < COMPOST_MAX_ATOMS; ++atom) {
                if (labels[atom] < 2U) {
                    ++sizes[labels[atom]];
                    if (first[labels[atom]] == UINT8_MAX) first[labels[atom]] = (uint8_t)atom;
                }
            }
            const uint8_t child_label = sizes[0] < sizes[1] || (sizes[0] == sizes[1] && first[0] < first[1])
                ? UINT8_C(0) : UINT8_C(1);
            double boundary_strength = 0.0;
            for (size_t edge_collection = 0U; edge_collection < 2U; ++edge_collection) {
                const compost_structure_t *boundary_edges = edge_collection == 0U ? organism->relations : organism->composites;
                const size_t boundary_count = edge_collection == 0U ? COMPOST_MAX_RELATIONS : COMPOST_MAX_COMPOSITES;
                for (size_t boundary_index = 0U; boundary_index < boundary_count; ++boundary_index) {
                    const compost_structure_t *boundary_edge = &boundary_edges[boundary_index];
                    if (boundary_edge->occupied && boundary_matches(boundary_edge->left, boundary_edge->right, left, right)) {
                        boundary_strength += boundary_edge->strength;
                    }
                }
            }
            const compost_structure_t *left_atom = atom_for_key(organism, left);
            const compost_structure_t *right_atom = atom_for_key(organism, right);
            if (left_atom == NULL || right_atom == NULL) continue;
            const double denominator = left_atom->strength + right_atom->strength + boundary_strength;
            const double ratio = denominator > 0.0 ? boundary_strength / denominator : 1.0;
            if (!finite(ratio) || ratio >= boundary_ratio_limit ||
                (found && (ratio > best_ratio || (ratio == best_ratio &&
                    (left > best_left || (left == best_left && right >= best_right)))))) continue;
            found = true;
            best_ratio = ratio;
            best_left = left;
            best_right = right;
            for (size_t atom = 0U; atom < COMPOST_MAX_ATOMS; ++atom) best_selected[atom] = labels[atom] == child_label;
        }
    }
    if (!found) return COMPOST_STATUS_INVALID_STATE;
    size_t count = 0U;
    for (size_t atom = 0U; atom < COMPOST_MAX_ATOMS; ++atom) if (best_selected[atom]) ++count;
    *child_atom_count = count;
    *selected_ratio = best_ratio;
    if (child_atom_capacity < count) return COMPOST_STATUS_BUFFER_TOO_SMALL;
    size_t output = 0U;
    for (size_t atom = 0U; atom < COMPOST_MAX_ATOMS; ++atom) if (best_selected[atom]) child_atoms[output++] = (uint8_t)atom;
    return COMPOST_STATUS_OK;
}

static bool local_component_lexicographically_less(
    const uint16_t labels[COMPOST_MAX_ATOMS],
    uint16_t left,
    uint16_t right
)
{
    for (size_t index = 0U; index < COMPOST_MAX_ATOMS; ++index) {
        const bool left_present = labels[index] == left;
        const bool right_present = labels[index] == right;
        if (left_present != right_present) return left_present;
    }
    return false;
}

static size_t local_reproduction_child_item_count(
    const compost_organism_t *organism,
    const bool selected[COMPOST_MAX_ATOMS]
)
{
    size_t count = 0U;
    for (size_t index = 0U; index < COMPOST_MAX_ATOMS; ++index) {
        if (organism->atoms[index].occupied && selected[(size_t)organism->atoms[index].left]) ++count;
    }
    for (size_t collection = 0U; collection < 2U; ++collection) {
        const compost_structure_t *structures = collection == 0U
            ? organism->relations : organism->composites;
        const size_t structure_count = collection == 0U ? COMPOST_MAX_RELATIONS : COMPOST_MAX_COMPOSITES;
        for (size_t index = 0U; index < structure_count; ++index) {
            const compost_structure_t *structure = &structures[index];
            if (structure->occupied && selected[(size_t)structure->left] &&
                selected[(size_t)structure->right]) ++count;
        }
    }
    return count;
}

static size_t local_reproduction_parent_item_count(
    const compost_organism_t *organism,
    const bool selected[COMPOST_MAX_ATOMS]
)
{
    size_t count = 0U;
    for (size_t index = 0U; index < COMPOST_MAX_ATOMS; ++index) {
        if (organism->atoms[index].occupied && !selected[(size_t)organism->atoms[index].left]) ++count;
    }
    for (size_t collection = 0U; collection < 2U; ++collection) {
        const compost_structure_t *structures = collection == 0U
            ? organism->relations : organism->composites;
        const size_t structure_count = collection == 0U ? COMPOST_MAX_RELATIONS : COMPOST_MAX_COMPOSITES;
        for (size_t index = 0U; index < structure_count; ++index) {
            const compost_structure_t *structure = &structures[index];
            if (structure->occupied && !selected[(size_t)structure->left] &&
                !selected[(size_t)structure->right]) ++count;
        }
    }
    return count;
}

compost_status_t compost_organism_select_local_reproduction(
    const compost_organism_t *organism,
    uint8_t *child_atoms,
    size_t child_atom_capacity,
    size_t *child_atom_count
)
{
    if (organism == NULL || child_atoms == NULL || child_atom_count == NULL ||
        !organism->initialized || organism->status != COMPOST_LIFECYCLE_ALIVE) {
        return COMPOST_STATUS_INVALID_ARGUMENT;
    }
    *child_atom_count = 0U;
    if (organism->body.atom_count < 3U || organism->body.structural_mass == 0U) {
        return COMPOST_STATUS_INVALID_STATE;
    }

    bool present[COMPOST_MAX_ATOMS] = {false};
    bool active[COMPOST_MAX_ATOMS] = {false};
    bool weighted[COMPOST_MAX_ATOMS] = {false};
    bool adjacency[COMPOST_MAX_ATOMS][COMPOST_MAX_ATOMS] = {{false}};
    double weights[COMPOST_MAX_ATOMS] = {0.0};
    size_t active_count = 0U;
    for (size_t index = 0U; index < COMPOST_MAX_ATOMS; ++index) {
        const compost_structure_t *atom = &organism->atoms[index];
        if (!atom->occupied) continue;
        present[(size_t)atom->left] = true;
        if (atom->strength >= 2.0) {
            active[(size_t)atom->left] = true;
            ++active_count;
        }
    }
    if (active_count < 3U) return COMPOST_STATUS_INVALID_STATE;
    for (size_t collection = 0U; collection < 2U; ++collection) {
        const compost_structure_t *structures = collection == 0U
            ? organism->relations : organism->composites;
        const size_t structure_count = collection == 0U ? COMPOST_MAX_RELATIONS : COMPOST_MAX_COMPOSITES;
        for (size_t index = 0U; index < structure_count; ++index) {
            const compost_structure_t *structure = &structures[index];
            if (!structure->occupied || structure->left == structure->right ||
                atom_for_key(organism, structure->left) == NULL ||
                atom_for_key(organism, structure->right) == NULL) continue;
            present[(size_t)structure->left] = true;
            present[(size_t)structure->right] = true;
            adjacency[(size_t)structure->left][(size_t)structure->right] = true;
            adjacency[(size_t)structure->right][(size_t)structure->left] = true;
            if (!weighted[(size_t)structure->left] || structure->strength < weights[(size_t)structure->left]) {
                weighted[(size_t)structure->left] = true;
                weights[(size_t)structure->left] = structure->strength;
            }
            if (!weighted[(size_t)structure->right] || structure->strength < weights[(size_t)structure->right]) {
                weighted[(size_t)structure->right] = true;
                weights[(size_t)structure->right] = structure->strength;
            }
        }
    }

    double weakest_weight = INFINITY;
    for (size_t member = 0U; member < COMPOST_MAX_ATOMS; ++member) {
        if (!present[member]) continue;
        const double value = weighted[member] ? weights[member] : 0.0;
        if (value < weakest_weight) weakest_weight = value;
    }
    if (!finite(weakest_weight)) return COMPOST_STATUS_INVALID_STATE;

    for (size_t boundary = 0U; boundary < COMPOST_MAX_ATOMS; ++boundary) {
        if (!present[boundary]) continue;
        const double boundary_weight = weighted[boundary] ? weights[boundary] : 0.0;
        if (boundary_weight != weakest_weight) continue;

        bool unseen[COMPOST_MAX_ATOMS] = {false};
        for (size_t member = 0U; member < COMPOST_MAX_ATOMS; ++member) {
            unseen[member] = active[member] && member != boundary;
        }
        uint16_t component_labels[COMPOST_MAX_ATOMS];
        for (size_t index = 0U; index < COMPOST_MAX_ATOMS; ++index) {
            component_labels[index] = UINT16_MAX;
        }
        size_t component_sizes[COMPOST_MAX_ATOMS] = {0U};
        size_t component_count = 0U;
        for (;;) {
            size_t seed = COMPOST_MAX_ATOMS;
            for (size_t member = 0U; member < COMPOST_MAX_ATOMS; ++member) {
                if (unseen[member]) {
                    seed = member;
                    break;
                }
            }
            if (seed == COMPOST_MAX_ATOMS) break;
            if (component_count >= COMPOST_MAX_ATOMS) return COMPOST_STATUS_INVALID_STATE;
            uint8_t queue[COMPOST_MAX_ATOMS] = {0U};
            size_t head = 0U;
            size_t tail = 0U;
            queue[tail++] = (uint8_t)seed;
            unseen[seed] = false;
            while (head < tail) {
                const size_t current = queue[head++];
                component_labels[current] = (uint16_t)component_count;
                ++component_sizes[component_count];
                for (size_t neighbour = 0U; neighbour < COMPOST_MAX_ATOMS; ++neighbour) {
                    if (unseen[neighbour] && adjacency[current][neighbour]) {
                        unseen[neighbour] = false;
                        queue[tail++] = (uint8_t)neighbour;
                    }
                }
            }
            ++component_count;
        }
        size_t order[COMPOST_MAX_ATOMS] = {0U};
        for (size_t index = 0U; index < component_count; ++index) order[index] = index;
        for (size_t left = 1U; left < component_count; ++left) {
            const size_t value = order[left];
            size_t right = left;
            while (right > 0U) {
                const size_t previous = order[right - 1U];
                const bool before = component_sizes[value] < component_sizes[previous] ||
                    (component_sizes[value] == component_sizes[previous] &&
                     local_component_lexicographically_less(
                         component_labels, (uint16_t)value, (uint16_t)previous
                     ));
                if (!before) break;
                order[right] = previous;
                --right;
            }
            order[right] = value;
        }
        for (size_t position = 0U; position < component_count; ++position) {
            const size_t component = order[position];
            bool selected[COMPOST_MAX_ATOMS] = {false};
            size_t selected_atoms = 0U;
            for (size_t member = 0U; member < COMPOST_MAX_ATOMS; ++member) {
                selected[member] = component_labels[member] == (uint16_t)component;
                if (selected[member]) ++selected_atoms;
            }
            const size_t child_items = local_reproduction_child_item_count(organism, selected);
            const size_t parent_items = local_reproduction_parent_item_count(organism, selected);
            const bool viable = selected_atoms > 0U && parent_items > 0U &&
                organism->body.atom_count + organism->body.relation_count + organism->body.composite_count >=
                    organism->config.reproduction_minimum_body &&
                child_items >= 2U && organism->reserve >= organism->config.birth_cost;
            if (!viable) continue;
            if (child_atom_capacity < selected_atoms) return COMPOST_STATUS_BUFFER_TOO_SMALL;
            size_t output = 0U;
            for (size_t member = 0U; member < COMPOST_MAX_ATOMS; ++member) {
                if (selected[member]) child_atoms[output++] = (uint8_t)member;
            }
            *child_atom_count = selected_atoms;
            return COMPOST_STATUS_OK;
        }
    }
    return COMPOST_STATUS_INVALID_STATE;
}

compost_status_t compost_organism_plan_division(
    const compost_organism_t *organism,
    compost_division_plan_t *plan
)
{
    if (organism == NULL || plan == NULL || !organism->initialized ||
        organism->status != COMPOST_LIFECYCLE_ALIVE) {
        return COMPOST_STATUS_INVALID_ARGUMENT;
    }
    memset(plan, 0, sizeof(*plan));
    size_t selected_count = 0U;
    double ratio = 0.0;
    const compost_status_t selection = compost_organism_select_partition(
        organism,
        organism->config.boundary_ratio_limit,
        plan->child_atoms,
        COMPOST_MAX_ATOMS,
        &selected_count,
        &ratio
    );
    if (selection == COMPOST_STATUS_INVALID_STATE) {
        return COMPOST_STATUS_OK;
    }
    if (selection != COMPOST_STATUS_OK) return selection;
    plan->candidate_found = true;
    plan->child_atom_count = selected_count;
    plan->boundary_ratio = ratio;
    bool selected[COMPOST_MAX_ATOMS] = {false};
    for (size_t index = 0U; index < selected_count; ++index) selected[(size_t)plan->child_atoms[index]] = true;
    for (size_t index = 0U; index < COMPOST_MAX_ATOMS; ++index) {
        const compost_structure_t *atom = &organism->atoms[index];
        if (!atom->occupied) continue;
        double *income = selected[(size_t)atom->left] ? &plan->child_income : &plan->parent_income;
        double *maintenance = selected[(size_t)atom->left] ? &plan->child_maintenance : &plan->parent_maintenance;
        *income += atom->income_rate;
        *maintenance += atom->maintenance;
    }
    for (size_t collection = 0U; collection < 2U; ++collection) {
        const compost_structure_t *structures = collection == 0U ? organism->relations : organism->composites;
        const size_t structure_count = collection == 0U ? COMPOST_MAX_RELATIONS : COMPOST_MAX_COMPOSITES;
        for (size_t index = 0U; index < structure_count; ++index) {
            const compost_structure_t *structure = &structures[index];
            if (!structure->occupied || atom_for_key(organism, structure->left) == NULL ||
                atom_for_key(organism, structure->right) == NULL) continue;
            const bool left_selected = selected[(size_t)structure->left];
            const bool right_selected = selected[(size_t)structure->right];
            if (left_selected && right_selected) {
                plan->child_income += structure->income_rate;
                plan->child_maintenance += structure->maintenance;
            } else if (!left_selected && !right_selected) {
                plan->parent_income += structure->income_rate;
                plan->parent_maintenance += structure->maintenance;
            } else {
                plan->boundary_maintenance += structure->maintenance;
            }
        }
    }
    plan->birth_gain = organism->config.division_horizon * plan->boundary_maintenance - organism->config.birth_cost;
    plan->allowed = finite(plan->child_income) && finite(plan->child_maintenance) &&
        finite(plan->parent_income) && finite(plan->parent_maintenance) && finite(plan->birth_gain) &&
        plan->child_income > plan->child_maintenance &&
        plan->parent_income > plan->parent_maintenance &&
        organism->reserve >= organism->config.birth_cost && plan->birth_gain > 0.0;
    return COMPOST_STATUS_OK;
}

compost_status_t compost_organism_partition(
    compost_organism_t *parent,
    compost_organism_t *child,
    uint64_t child_id,
    const uint8_t *child_atoms,
    size_t child_atom_count,
    double birth_cost,
    compost_division_result_t *result
)
{
    if (parent == NULL || child == NULL || result == NULL ||
        !parent->initialized || parent->status != COMPOST_LIFECYCLE_ALIVE ||
        child->initialized || child_atoms == NULL || child_atom_count == 0U ||
        child_atom_count >= COMPOST_MAX_ATOMS || !finite(birth_cost) || birth_cost < 0.0 ||
        parent->reserve < birth_cost || child_id == parent->organism_id ||
        parent->territory.depth >= parent->config.max_territory_depth ||
        parent->territory.local_birth_counter == UINT64_MAX) {
        return COMPOST_STATUS_INVALID_ARGUMENT;
    }
    if (compost_organism_verify_material_conservation(parent) != COMPOST_STATUS_OK) {
        return COMPOST_STATUS_INVALID_STATE;
    }
    bool selected[COMPOST_MAX_ATOMS] = {false};
    size_t selected_count = 0U;
    for (size_t index = 0U; index < child_atom_count; ++index) {
        const uint8_t key = child_atoms[index];
        if (selected[(size_t)key] || !find_structure(parent->atoms, COMPOST_MAX_ATOMS, key, 0U)) {
            return COMPOST_STATUS_INVALID_ARGUMENT;
        }
        selected[(size_t)key] = true;
        ++selected_count;
    }
    if (selected_count >= parent->body.atom_count) {
        return COMPOST_STATUS_INVALID_ARGUMENT;
    }
    uint64_t moved_mass = 0U;
    uint64_t cross_mass = 0U;
    uint64_t cross_count = 0U;
    if (partition_mass(parent, selected, &moved_mass, &cross_mass, &cross_count) != COMPOST_STATUS_OK ||
        cross_count > COMPOST_MAX_GUT_CHUNKS ||
        parent->gut_count > COMPOST_MAX_GUT_CHUNKS - (uint32_t)cross_count ||
        moved_mass > parent->body.structural_mass ||
        cross_mass > parent->body.structural_mass - moved_mass ||
        parent->material_flow.structural_transferred_out > UINT64_MAX - moved_mass ||
        parent->material_flow.resorbed_mass > UINT64_MAX - cross_mass ||
        parent->reserve - birth_cost < 0.0) {
        return COMPOST_STATUS_INVALID_STATE;
    }
    compost_organism_t next_parent = *parent;
    if (compost_organism_init(child, &parent->config, &parent->allocator, child_id) != COMPOST_STATUS_OK) {
        return COMPOST_STATUS_OUT_OF_MEMORY;
    }
    child->parent_id = parent->organism_id;
    child->has_parent = true;
    child->generation = parent->generation == UINT64_MAX ? UINT64_MAX : parent->generation + UINT64_C(1);
    if (parent->generation == UINT64_MAX) {
        compost_organism_destroy(child);
        return COMPOST_STATUS_INVALID_STATE;
    }
    child->cursor = parent->cursor;
    child->reserve = 0.0;
    child->territory.depth = parent->territory.depth + 1U;
    memcpy(child->territory.path, parent->territory.path, parent->territory.depth);
    child->territory.path[parent->territory.depth] = UINT8_C(1);
    child->territory.organism_id = child_id;
    child->territory.alive = true;
    next_parent.territory.path[next_parent.territory.depth] = UINT8_C(0);
    next_parent.territory.depth += 1U;
    next_parent.territory.local_birth_counter += UINT64_C(1);

    for (size_t index = 0U; index < COMPOST_MAX_ATOMS; ++index) {
        compost_structure_t *structure = &next_parent.atoms[index];
        if (structure->occupied && selected[(size_t)structure->left]) {
            child->atoms[index] = *structure;
            memset(structure, 0, sizeof(*structure));
            --next_parent.body.atom_count;
            ++child->body.atom_count;
        }
    }
    for (size_t collection = 0U; collection < 2U; ++collection) {
        compost_structure_t *structures = collection == 0U ? next_parent.relations : next_parent.composites;
        compost_structure_t *child_structures = collection == 0U ? child->relations : child->composites;
        const size_t count = collection == 0U ? COMPOST_MAX_RELATIONS : COMPOST_MAX_COMPOSITES;
        for (size_t index = 0U; index < count; ++index) {
            compost_structure_t *structure = &structures[index];
            if (!structure->occupied) continue;
            const bool left_selected = selected[(size_t)structure->left];
            const bool right_selected = selected[(size_t)structure->right];
            if (left_selected && right_selected) {
                child_structures[index] = *structure;
                uint64_t mass = 0U;
                if (compost_structural_mass(structure->strength, &mass) != COMPOST_STATUS_OK) {
                    compost_organism_destroy(child);
                    return COMPOST_STATUS_INVALID_STATE;
                }
                memset(structure, 0, sizeof(*structure));
                next_parent.body.structural_mass -= mass;
                if (collection == 0U) {
                    --next_parent.body.relation_count;
                    ++child->body.relation_count;
                } else {
                    --next_parent.body.composite_count;
                    ++child->body.composite_count;
                }
                child->body.structural_mass += mass;
            } else if (left_selected != right_selected) {
                uint64_t ignored = 0U;
                if (remove_structure_entry(&next_parent, structure, &ignored) != COMPOST_STATUS_OK) {
                    compost_organism_destroy(child);
                    return COMPOST_STATUS_INVALID_STATE;
                }
            }
        }
    }
    next_parent.reserve -= birth_cost;
    next_parent.material_flow.structural_transferred_out += moved_mass;
    child->material_flow.structural_transferred_in = moved_mass;
    compost_activity_counters_t division_counters = {0};
    division_counters.division_events = UINT64_C(1);
    if (compost_activity_ledger_add(
            &next_parent.activity,
            &division_counters,
            next_parent.body.structural_mass,
            &DEFAULT_ACTIVITY_COSTS
        ) != COMPOST_STATUS_OK ||
        settle_activity_debt(&next_parent) != COMPOST_STATUS_OK) {
        compost_organism_destroy(child);
        return COMPOST_STATUS_INVALID_STATE;
    }
    *result = (compost_division_result_t){
        moved_mass,
        cross_mass,
        next_parent.reserve
    };
    *parent = next_parent;
    return COMPOST_STATUS_OK;
}

static int structure_kind_order(compost_structure_kind_t kind)
{
    if (kind == COMPOST_STRUCTURE_ATOM) return 0;
    if (kind == COMPOST_STRUCTURE_COMPOSITE) return 1;
    return 2;
}

static bool weaker(const compost_structure_t *left, const compost_structure_t *right)
{
    if (right == NULL) return true;
    if (left->strength != right->strength) return left->strength < right->strength;
    if (left->evidence != right->evidence) return left->evidence < right->evidence;
    if (left->income_rate != right->income_rate) return left->income_rate < right->income_rate;
    if (left->kind != right->kind) return structure_kind_order(left->kind) < structure_kind_order(right->kind);
    if (left->left != right->left) return left->left < right->left;
    return left->right < right->right;
}

static compost_structure_t *weakest_structure(compost_organism_t *organism)
{
    compost_structure_t *best = NULL;
    for (size_t i = 0U; i < COMPOST_MAX_ATOMS; ++i)
        if (organism->atoms[i].occupied && weaker(&organism->atoms[i], best)) best = &organism->atoms[i];
    for (size_t i = 0U; i < COMPOST_MAX_RELATIONS; ++i)
        if (organism->relations[i].occupied && weaker(&organism->relations[i], best)) best = &organism->relations[i];
    for (size_t i = 0U; i < COMPOST_MAX_COMPOSITES; ++i)
        if (organism->composites[i].occupied && weaker(&organism->composites[i], best)) best = &organism->composites[i];
    return best;
}

static compost_status_t remove_structure_entry(
    compost_organism_t *organism,
    compost_structure_t *structure,
    uint64_t *resorbed_mass
)
{
    uint64_t mass = 0U;
    if (structure->kind != COMPOST_STRUCTURE_ATOM &&
        compost_structural_mass(structure->strength, &mass) != COMPOST_STATUS_OK) {
        return COMPOST_STATUS_INVALID_ARGUMENT;
    }
    if (organism->body.structural_mass < mass ||
        (mass > 0U && compost_organism_enqueue_resorbed(organism, mass) != COMPOST_STATUS_OK)) {
        return COMPOST_STATUS_INVALID_ARGUMENT;
    }
    organism->body.structural_mass -= mass;
    if (structure->kind == COMPOST_STRUCTURE_ATOM) --organism->body.atom_count;
    else if (structure->kind == COMPOST_STRUCTURE_RELATION) --organism->body.relation_count;
    else --organism->body.composite_count;
    structure->occupied = false;
    return add_u64(*resorbed_mass, mass, resorbed_mass)
        ? COMPOST_STATUS_OK : COMPOST_STATUS_INVALID_ARGUMENT;
}

static compost_status_t remove_weakest_for_pressure(
    compost_organism_t *organism,
    uint64_t *resorbed_mass
)
{
    compost_structure_t *target = weakest_structure(organism);
    if (target == NULL) return COMPOST_STATUS_INVALID_STATE;
    const compost_structure_kind_t kind = target->kind;
    const uint8_t symbol = target->left;
    if (kind == COMPOST_STRUCTURE_ATOM) {
        for (size_t index = 0U; index < COMPOST_MAX_RELATIONS; ++index) {
            compost_structure_t *edge = &organism->relations[index];
            if (edge->occupied && (edge->left == symbol || edge->right == symbol) &&
                remove_structure_entry(organism, edge, resorbed_mass) != COMPOST_STATUS_OK) {
                return COMPOST_STATUS_INVALID_STATE;
            }
        }
        for (size_t index = 0U; index < COMPOST_MAX_COMPOSITES; ++index) {
            compost_structure_t *edge = &organism->composites[index];
            if (edge->occupied && (edge->left == symbol || edge->right == symbol) &&
                remove_structure_entry(organism, edge, resorbed_mass) != COMPOST_STATUS_OK) {
                return COMPOST_STATUS_INVALID_STATE;
            }
        }
    }
    return remove_structure_entry(organism, target, resorbed_mass);
}

compost_status_t compost_organism_weaken_weakest(
    compost_organism_t *organism,
    bool *changed,
    uint64_t *resorbed_mass
)
{
    if (organism == NULL || changed == NULL || resorbed_mass == NULL || !organism->initialized) {
        return COMPOST_STATUS_INVALID_ARGUMENT;
    }
    *changed = false;
    *resorbed_mass = 0U;
    compost_organism_t next = *organism;
    compost_structure_t *target = weakest_structure(&next);
    if (target == NULL) {
        return COMPOST_STATUS_OK;
    }
    if (target->strength > 1.0) {
        uint64_t before_mass = 0U;
        uint64_t after_mass = 0U;
        if (target->kind != COMPOST_STRUCTURE_ATOM) {
            if (compost_structural_mass(target->strength, &before_mass) != COMPOST_STATUS_OK ||
                compost_structural_mass(target->strength - 1.0, &after_mass) != COMPOST_STATUS_OK ||
                after_mass > before_mass || next.body.structural_mass < before_mass - after_mass) {
                return COMPOST_STATUS_INVALID_STATE;
            }
        }
        target->strength -= 1.0;
        if (target->kind != COMPOST_STRUCTURE_ATOM && before_mass > after_mass) {
            const uint64_t decrease = before_mass - after_mass;
            if (compost_organism_enqueue_resorbed(&next, decrease) != COMPOST_STATUS_OK ||
                !add_u64(*resorbed_mass, decrease, resorbed_mass)) {
                return COMPOST_STATUS_INVALID_ARGUMENT;
            }
            next.body.structural_mass -= decrease;
        }
        *changed = true;
    } else {
        const compost_structure_kind_t kind = target->kind;
        const uint8_t symbol = target->left;
        if (kind == COMPOST_STRUCTURE_ATOM) {
            for (size_t i = 0U; i < COMPOST_MAX_RELATIONS; ++i) {
                compost_structure_t *edge = &next.relations[i];
                if (edge->occupied && (edge->left == symbol || edge->right == symbol) &&
                    remove_structure_entry(&next, edge, resorbed_mass) != COMPOST_STATUS_OK) {
                    return COMPOST_STATUS_INVALID_ARGUMENT;
                }
            }
            for (size_t i = 0U; i < COMPOST_MAX_COMPOSITES; ++i) {
                compost_structure_t *edge = &next.composites[i];
                if (edge->occupied && (edge->left == symbol || edge->right == symbol) &&
                    remove_structure_entry(&next, edge, resorbed_mass) != COMPOST_STATUS_OK) {
                    return COMPOST_STATUS_INVALID_ARGUMENT;
                }
            }
        }
        if (remove_structure_entry(&next, target, resorbed_mass) != COMPOST_STATUS_OK) {
            return COMPOST_STATUS_INVALID_ARGUMENT;
        }
        *changed = true;
    }
    *organism = next;
    return COMPOST_STATUS_OK;
}
