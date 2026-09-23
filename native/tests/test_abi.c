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
    compost_context_t *context = NULL;
    compost_snapshot_t snapshot = {0};
    const uint8_t food[] = {4U, 5U};
    const double nutrition[] = {1.0, 1.0};
    const compost_step_input_t input = {food, nutrition, sizeof(food)};
    compost_step_result_t result = {0};
    compost_context_t *child = NULL;
    compost_division_result_t division = {0};
    compost_division_plan_t try_plan = {0};
    compost_division_result_t try_result = {0};
    const uint8_t child_atoms[] = {4U};
    uint8_t selected_atoms[COMPOST_MAX_ATOMS] = {0};
    size_t selected_count = 0U;
    double selected_ratio = 0.0;
    compost_division_plan_t plan = {0};
    uint64_t initial_digest = 0U;
    uint64_t changed_digest = 0U;
    if (COMPOST_NATIVE_ABI_VERSION != UINT32_C(3) ||
        compost_config_default(&config) != COMPOST_STATUS_OK ||
        compost_create(&config, UINT64_C(12), &context) != COMPOST_STATUS_OK ||
        context == NULL ||
        compost_context_verify_material_conservation(context) != COMPOST_STATUS_OK ||
        compost_context_digest(context, &input, &result) != COMPOST_STATUS_OK ||
        result.consumed_bytes != 2U ||
        compost_context_snapshot(context, &snapshot) != COMPOST_STATUS_OK ||
        snapshot.organism_id != UINT64_C(12) || snapshot.cursor != 2U) {
        compost_destroy(context);
        return fail("opaque ABI");
    }
    if (compost_context_try_divide(context, UINT64_C(14), &child, &try_plan, &try_result) != COMPOST_STATUS_OK ||
        child != NULL || try_plan.candidate_found || try_plan.allowed ||
        try_result.child_structural_mass != 0U) {
        compost_destroy(child);
        compost_destroy(context);
        return fail("opaque try-division no-op");
    }
    if (compost_context_select_partition(context, 0.5, selected_atoms, COMPOST_MAX_ATOMS,
                                         &selected_count, &selected_ratio) != COMPOST_STATUS_OK ||
        selected_count != 1U || selected_atoms[0] != 4U || selected_ratio < 0.3333 || selected_ratio > 0.3334) {
        compost_destroy(context);
        return fail("opaque selector ABI");
    }
    if (compost_context_plan_division(context, &plan) != COMPOST_STATUS_OK || plan.candidate_found) {
        compost_destroy(context);
        return fail("opaque viability ABI");
    }
    if (compost_context_partition(context, UINT64_C(13), child_atoms, 1U, 1.0, &child, &division) != COMPOST_STATUS_OK ||
        child == NULL || compost_context_snapshot(child, &snapshot) != COMPOST_STATUS_OK ||
        snapshot.parent_id != UINT64_C(12) || !snapshot.has_parent || snapshot.reserve != 0.0 ||
        snapshot.body.atom_count != UINT64_C(1) || division.cross_split_mass == 0U) {
        compost_destroy(child);
        compost_destroy(context);
        return fail("opaque partition ABI");
    }
    compost_destroy(child);
    initial_digest = compost_context_state_digest(context);
    if (initial_digest == UINT64_C(0)) {
        compost_destroy(context);
        return fail("state digest initialization");
    }
    if (compost_context_digest(context, &input, &result) != COMPOST_STATUS_OK) {
        compost_destroy(context);
        return fail("state digest transition");
    }
    changed_digest = compost_context_state_digest(context);
    if (changed_digest == initial_digest || compost_context_state_digest(NULL) != UINT64_C(0)) {
        compost_destroy(context);
        return fail("state digest stability");
    }
    compost_destroy(context);
    compost_config_t division_config = config;
    division_config.boundary_ratio_limit = 0.5;
    division_config.birth_reserve = 10.0;
    compost_context_t *division_context = NULL;
    compost_context_t *division_child = NULL;
    compost_division_plan_t automatic_plan = {0};
    compost_division_result_t automatic_result = {0};
    if (compost_create(&division_config, UINT64_C(20), &division_context) != COMPOST_STATUS_OK ||
        compost_context_digest(division_context, &input, &result) != COMPOST_STATUS_OK ||
        compost_context_try_divide(
            division_context, UINT64_C(21), &division_child, &automatic_plan, &automatic_result
        ) != COMPOST_STATUS_OK ||
        division_child == NULL || !automatic_plan.candidate_found || !automatic_plan.allowed ||
        automatic_plan.child_atom_count != 1U || automatic_result.cross_split_mass == 0U ||
        compost_context_verify_material_conservation(division_context) != COMPOST_STATUS_OK ||
        compost_context_verify_material_conservation(division_child) != COMPOST_STATUS_OK) {
        compost_destroy(division_child);
        compost_destroy(division_context);
        return fail("opaque try-division commit");
    }
    compost_destroy(division_child);
    compost_destroy(division_context);
    if (compost_context_snapshot(NULL, &snapshot) != COMPOST_STATUS_INVALID_ARGUMENT) {
        return fail("opaque ABI invalid handle");
    }
    if (compost_context_verify_material_conservation(NULL) != COMPOST_STATUS_INVALID_ARGUMENT) {
        return fail("opaque conservation invalid handle");
    }
    bool changed = true;
    uint64_t resorbed_mass = UINT64_C(9);
    if (compost_context_weaken_weakest(NULL, &changed, &resorbed_mass) != COMPOST_STATUS_INVALID_ARGUMENT ||
        changed != true || resorbed_mass != UINT64_C(9)) {
        return fail("opaque weakest invalid handle");
    }
    if (compost_context_try_divide(NULL, 1U, &child, &try_plan, &try_result) != COMPOST_STATUS_INVALID_ARGUMENT) {
        return fail("opaque try-division invalid handle");
    }
    compost_context_t *combined_context = NULL;
    compost_context_t *combined_child = NULL;
    compost_cycle_result_t combined_cycle = {0};
    compost_division_plan_t combined_plan = {0};
    compost_division_result_t combined_division = {0};
    if (compost_create(&division_config, UINT64_C(30), &combined_context) != COMPOST_STATUS_OK ||
        compost_context_step_and_try_divide(
            combined_context, &input, UINT64_C(31), &combined_child,
            &combined_cycle, &combined_plan, &combined_division
        ) != COMPOST_STATUS_OK ||
        combined_child == NULL || combined_cycle.digestion.consumed_bytes != 2U ||
        !combined_plan.candidate_found || !combined_plan.allowed ||
        combined_division.cross_split_mass == 0U ||
        compost_context_verify_material_conservation(combined_context) != COMPOST_STATUS_OK ||
        compost_context_verify_material_conservation(combined_child) != COMPOST_STATUS_OK) {
        compost_destroy(combined_child);
        compost_destroy(combined_context);
        return fail("opaque step-and-division ABI");
    }
    compost_destroy(combined_child);
    compost_destroy(combined_context);
    return 0;
}
