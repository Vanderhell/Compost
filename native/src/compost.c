#include "compost/compost.h"

#include <math.h>
#include <stdlib.h>
#include <string.h>

struct compost_context {
    compost_organism_t organism;
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

static const compost_activity_costs_t DEFAULT_ACTIVITY_COSTS = {
    0.0, 0.001, 0.002, 0.002, 0.08, 0.01, 0.12, 0.02,
    0.01, 0.10, 0.50, 0.001, 2.0, 0.01
};

static bool valid_config(const compost_config_t *config)
{
    return config != NULL &&
           config->abi_version == COMPOST_NATIVE_ABI_VERSION &&
           config->max_body_mass > 0U &&
           config->max_territory_depth <= COMPOST_MAX_TERRITORY_DEPTH &&
           config->income_decay > 0.0 && config->income_decay < 1.0 &&
           finite(config->atom_income) && config->atom_income > 0.0 &&
           finite(config->relation_income) && config->relation_income > 0.0 &&
           finite(config->atom_maintenance) && config->atom_maintenance > 0.0 &&
           finite(config->relation_maintenance) && config->relation_maintenance > 0.0 &&
           finite(config->atom_formation_cost) && config->atom_formation_cost > 0.0 &&
           finite(config->relation_formation_cost) && config->relation_formation_cost > 0.0 &&
           finite(config->birth_reserve) && config->birth_reserve >= 0.0;
}

compost_status_t compost_create(
    const compost_config_t *config,
    uint64_t organism_id,
    compost_context_t **context
)
{
    if (context == NULL || !valid_config(config)) {
        return COMPOST_STATUS_INVALID_ARGUMENT;
    }
    *context = NULL;
    compost_context_t *created = malloc(sizeof(*created));
    if (created == NULL) {
        return COMPOST_STATUS_OUT_OF_MEMORY;
    }
    memset(created, 0, sizeof(*created));
    const compost_status_t status = compost_organism_init(&created->organism, config, NULL, organism_id);
    if (status != COMPOST_STATUS_OK) {
        free(created);
        return status;
    }
    *context = created;
    return COMPOST_STATUS_OK;
}

void compost_destroy(compost_context_t *context)
{
    if (context == NULL) return;
    compost_organism_destroy(&context->organism);
    free(context);
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
    return compost_organism_state_digest(&context->organism);
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
    config->atom_maintenance = 0.25;
    config->relation_maintenance = 0.5;
    config->atom_formation_cost = 0.35;
    config->relation_formation_cost = 1.25;
    config->birth_reserve = 1.0;
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
    digest = digest_double(digest, config->atom_maintenance);
    digest = digest_double(digest, config->relation_maintenance);
    digest = digest_double(digest, config->atom_formation_cost);
    digest = digest_double(digest, config->relation_formation_cost);
    return digest_double(digest, config->birth_reserve);
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
            atom = free_structure(next.atoms, COMPOST_MAX_ATOMS);
            if (atom == NULL || !add_double(next.reserve, atom_gain, &next.reserve)) {
                return COMPOST_STATUS_INVALID_ARGUMENT;
            }
            if (next.body.atom_count > 0U && next.reserve < next.config.atom_formation_cost) {
                next.reserve -= atom_gain;
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
        compost_structure_t *relation = find_structure(next.relations, COMPOST_MAX_RELATIONS, left, right);
        const double relation_gain = next.config.relation_income * pair_nutrition;
        if (!finite(relation_gain)) {
            return COMPOST_STATUS_INVALID_ARGUMENT;
        }
        if (relation == NULL) {
            if (next.reserve < next.config.relation_formation_cost) {
                continue;
            }
            relation = free_structure(next.relations, COMPOST_MAX_RELATIONS);
            if (relation == NULL || !add_double(next.reserve, -next.config.relation_formation_cost, &next.reserve)) {
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

static uint64_t structure_count(const compost_organism_t *organism)
{
    return organism->body.atom_count + organism->body.relation_count + organism->body.composite_count;
}

static compost_status_t append_resorption_chunk(compost_organism_t *organism, uint64_t mass)
{
    if (mass == 0U) return COMPOST_STATUS_OK;
    if (organism->gut_count >= COMPOST_MAX_GUT_CHUNKS) return COMPOST_STATUS_INVALID_STATE;
    const uint32_t slot = (organism->gut_head + organism->gut_count) % COMPOST_MAX_GUT_CHUNKS;
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
    next_result.required = structure_maintenance(&next);
    if (!finite(next_result.required)) {
        return COMPOST_STATUS_INVALID_ARGUMENT;
    }
    next_result.paid = next.reserve < next_result.required ? next.reserve : next_result.required;
    next_result.deficit = next_result.required - next_result.paid;
    next.reserve -= next_result.paid;
    for (size_t index = 0U; index < COMPOST_MAX_ATOMS; ++index) {
        if (next.atoms[index].occupied && forget_structure(&next, &next.atoms[index], &next_result.resorbed_mass) != COMPOST_STATUS_OK) {
            return COMPOST_STATUS_INVALID_ARGUMENT;
        }
    }
    for (size_t index = 0U; index < COMPOST_MAX_RELATIONS; ++index) {
        if (next.relations[index].occupied && forget_structure(&next, &next.relations[index], &next_result.resorbed_mass) != COMPOST_STATUS_OK) {
            return COMPOST_STATUS_INVALID_ARGUMENT;
        }
    }
    for (size_t index = 0U; index < COMPOST_MAX_COMPOSITES; ++index) {
        if (next.composites[index].occupied && forget_structure(&next, &next.composites[index], &next_result.resorbed_mass) != COMPOST_STATUS_OK) {
            return COMPOST_STATUS_INVALID_ARGUMENT;
        }
    }
    if (append_resorption_chunk(&next, next_result.resorbed_mass) != COMPOST_STATUS_OK) {
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

compost_status_t compost_organism_enqueue_resorbed(
    compost_organism_t *organism,
    uint64_t mass
)
{
    if (organism == NULL || !organism->initialized || mass == 0U) {
        return COMPOST_STATUS_INVALID_ARGUMENT;
    }
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

static bool weaker(const compost_structure_t *left, const compost_structure_t *right)
{
    if (right == NULL) return true;
    if (left->strength != right->strength) return left->strength < right->strength;
    if (left->evidence != right->evidence) return left->evidence < right->evidence;
    if (left->income_rate != right->income_rate) return left->income_rate < right->income_rate;
    if (left->kind != right->kind) return left->kind < right->kind;
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
