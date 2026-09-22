#include "compost/compost.h"

#include <stdio.h>

static int fail(const char *message)
{
    (void)fprintf(stderr, "FAIL: %s\n", message);
    return 1;
}

int main(void)
{
    compost_config_t config = {0};
    compost_organism_t organism = {0};
    compost_snapshot_t snapshot = {0};
    if (compost_config_default(&config) != COMPOST_STATUS_OK ||
        compost_organism_init(&organism, &config, NULL, UINT64_C(7)) != COMPOST_STATUS_OK) {
        return fail("setup");
    }
    organism.generation = UINT64_C(3);
    organism.cursor = UINT64_C(11);
    organism.reserve = 2.5;
    organism.body.atom_count = UINT64_C(4);
    organism.body.structural_mass = UINT64_C(9);
    organism.territory.depth = 2U;
    organism.territory.path[0] = 1U;
    organism.territory.path[1] = 0U;
    if (compost_organism_snapshot(&organism, &snapshot) != COMPOST_STATUS_OK) {
        return fail("snapshot");
    }
    if (snapshot.organism_id != UINT64_C(7) || snapshot.generation != UINT64_C(3) ||
        snapshot.cursor != UINT64_C(11) || snapshot.reserve != 2.5 ||
        snapshot.body.atom_count != UINT64_C(4) || snapshot.body.structural_mass != UINT64_C(9) ||
        snapshot.territory.depth != 2U || snapshot.territory.path[0] != 1U ||
        snapshot.territory.path[1] != 0U) {
        return fail("snapshot values");
    }
    compost_organism_destroy(&organism);
    if (compost_organism_snapshot(&organism, &snapshot) != COMPOST_STATUS_INVALID_STATE) {
        return fail("destroyed snapshot rejection");
    }
    compost_activity_costs_t costs = {
        0.0, 0.001, 0.002, 0.002, 0.08, 0.01, 0.12, 0.02,
        0.01, 0.10, 0.50, 0.001, 2.0, 0.01
    };
    compost_activity_counters_t counters = {0};
    counters.bytes_eaten = 1024U;
    counters.processed_bytes = 1024U;
    counters.relations_created = 2U;
    compost_activity_ledger_t ledger = {0};
    if (compost_activity_ledger_add(&ledger, &counters, 256U, &costs) != COMPOST_STATUS_OK ||
        ledger.counters.bytes_eaten != 1024U || ledger.counters.relations_created != 2U ||
        ledger.metabolic_debt != 0.161) {
        return fail("activity ledger");
    }
    compost_forgetting_delta_t forgetting = {0};
    if (compost_forgetting_delta(5.0, 0.0, 0.5, 0.8, &forgetting) != COMPOST_STATUS_OK ||
        forgetting.strength_after != 4.0 || forgetting.income_rate_after != 0.0) {
        return fail("forgetting delta");
    }
    uint64_t budget = 0U;
    if (compost_maintenance_weakening_budget(1.0, 4U, &budget) != COMPOST_STATUS_OK || budget != 1U ||
        compost_maintenance_weakening_budget(0.0, 4U, &budget) != COMPOST_STATUS_OK || budget != 0U) {
        return fail("weakening budget");
    }
    const uint8_t food[] = {1U, 2U, 1U};
    const double nutrition[] = {1.0, 1.0, 1.0};
    const compost_step_input_t input = {food, nutrition, sizeof(food)};
    compost_step_result_t step = {0};
    compost_organism_t digesting = {0};
    if (compost_organism_init(&digesting, &config, NULL, UINT64_C(8)) != COMPOST_STATUS_OK ||
        compost_organism_digest(&digesting, &input, &step) != COMPOST_STATUS_OK ||
        step.consumed_bytes != 3U || step.assimilated_mass != 3U ||
        step.relations_created != 2U || digesting.body.atom_count != 2U ||
        digesting.body.relation_count != 2U || digesting.cursor != 3U ||
        digesting.material_flow.rejected_mass != 0U) {
        return fail("deterministic digest");
    }
    digesting.reserve = 10.0;
    compost_maintenance_result_t maintenance = {0};
    if (compost_organism_maintenance(&digesting, &maintenance) != COMPOST_STATUS_OK ||
        maintenance.required <= 0.0 || maintenance.paid != maintenance.required ||
        maintenance.deficit != 0.0 || digesting.age_in_cycles != 1U ||
        digesting.status != COMPOST_LIFECYCLE_ALIVE) {
        return fail("maintenance slice");
    }
    if (compost_organism_enqueue_resorbed(&digesting, 10U) != COMPOST_STATUS_OK ||
        digesting.gut_count != 1U || digesting.material_flow.resorbed_mass != 10U) {
        return fail("resorption enqueue");
    }
    uint64_t processed = 0U;
    if (compost_organism_process_resorption(&digesting, 4U, &processed) != COMPOST_STATUS_OK ||
        processed != 4U || digesting.gut_count != 1U ||
        digesting.gut[digesting.gut_head].mass != 6U ||
        digesting.material_flow.resorption_expelled_mass != 4U) {
        return fail("resorption FIFO");
    }
    compost_organism_destroy(&digesting);
    return 0;
}
