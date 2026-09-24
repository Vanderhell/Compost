#include "compost/compost.h"

#include <math.h>
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
    const compost_step_input_t empty_input = {NULL, NULL, 0U};
    compost_step_result_t result = {0};
    compost_cycle_result_t lifecycle_result = {0};
    compost_context_t *child = NULL;
    compost_context_t *batch_context = NULL;
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
    uint64_t schedule_threshold = 0U;
    uint64_t schedule_steps = 0U;
    uint64_t schedule_remaining = 0U;
    compost_metabolic_snapshot_t metabolic = {0};
    compost_context_t *lifecycle_context = NULL;
    uint64_t due_steps = 0U;
    uint64_t remaining_progress = 0U;
    compost_config_t invalid_config = {0};
    if (compost_config_default(NULL) != COMPOST_STATUS_INVALID_ARGUMENT ||
        compost_create(NULL, UINT64_C(1), &context) != COMPOST_STATUS_INVALID_ARGUMENT ||
        compost_config_default(&invalid_config) != COMPOST_STATUS_OK ||
        compost_create(&invalid_config, UINT64_C(1), NULL) != COMPOST_STATUS_INVALID_ARGUMENT) {
        return fail("public ABI null-argument validation");
    }
    if (compost_metabolic_schedule(UINT64_C(64), UINT64_C(4), UINT64_C(65),
                                   &schedule_threshold, &schedule_steps,
                                   &schedule_remaining) != COMPOST_STATUS_OK ||
        schedule_threshold != UINT64_C(64) || schedule_steps != UINT64_C(1) ||
        schedule_remaining != UINT64_C(1)) {
        return fail("metabolic schedule");
    }
    schedule_threshold = UINT64_C(9);
    schedule_steps = UINT64_C(9);
    schedule_remaining = UINT64_C(9);
    if (compost_metabolic_schedule(0U, 1U, 1U, &schedule_threshold, &schedule_steps,
                                   &schedule_remaining) != COMPOST_STATUS_INVALID_ARGUMENT ||
        schedule_threshold != UINT64_C(9) || schedule_steps != UINT64_C(9) ||
        schedule_remaining != UINT64_C(9)) {
        return fail("metabolic schedule validation");
    }
    if (COMPOST_NATIVE_ABI_VERSION != UINT32_C(4) ||
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
    uint64_t batch_executed = UINT64_C(99);
    compost_cycle_result_t batch_result = {0};
    if (compost_create(&config, UINT64_C(17), &batch_context) != COMPOST_STATUS_OK ||
        compost_context_digest(batch_context, &input, &result) != COMPOST_STATUS_OK ||
        compost_context_run_due_lifecycle(batch_context, UINT64_C(2), &batch_result,
                                          &batch_executed) != COMPOST_STATUS_OK ||
        batch_executed != UINT64_C(2) ||
        batch_result.status_after != COMPOST_LIFECYCLE_ALIVE) {
        compost_destroy(batch_context);
        compost_destroy(context);
        return fail("native due lifecycle batch");
    }
    compost_destroy(batch_context);
    compost_cycle_result_t invalid_batch_result = {0};
    invalid_batch_result.status_after = COMPOST_LIFECYCLE_DEAD;
    uint64_t invalid_batch_executed = UINT64_C(77);
    if (compost_context_run_due_lifecycle(
            NULL, UINT64_C(1), &invalid_batch_result, &invalid_batch_executed
        ) != COMPOST_STATUS_INVALID_ARGUMENT ||
        invalid_batch_result.status_after != COMPOST_LIFECYCLE_DEAD ||
        invalid_batch_executed != UINT64_C(77)) {
        compost_destroy(context);
        return fail("native due lifecycle invalid handle");
    }
    if (compost_context_metabolic_snapshot(context, &metabolic) != COMPOST_STATUS_OK ||
        metabolic.progress != 0U || metabolic.steps != 0U ||
        compost_context_accumulate_metabolic_progress(
            context, UINT64_C(65), UINT64_C(64), UINT64_C(4), &due_steps, &remaining_progress
        ) != COMPOST_STATUS_OK || due_steps != 1U || remaining_progress != 1U ||
        compost_context_metabolic_snapshot(context, &metabolic) != COMPOST_STATUS_OK ||
        metabolic.progress != 1U || metabolic.steps != 0U) {
        compost_destroy(context);
        return fail("metabolic context accounting");
    }
    due_steps = UINT64_C(9);
    remaining_progress = UINT64_C(9);
    if (compost_context_accumulate_metabolic_progress(
            context, UINT64_MAX, UINT64_C(64), UINT64_C(4), &due_steps, &remaining_progress
        ) != COMPOST_STATUS_INVALID_ARGUMENT || due_steps != UINT64_C(9) ||
        remaining_progress != UINT64_C(9) ||
        compost_context_metabolic_snapshot(context, &metabolic) != COMPOST_STATUS_OK ||
        metabolic.progress != 1U || metabolic.steps != 0U) {
        compost_destroy(context);
        return fail("metabolic context transaction");
    }
    compost_snapshot_t restore_snapshot = {0};
    compost_metabolic_snapshot_t restore_metabolic = {0};
    compost_context_t *restored_context = NULL;
    compost_status_t restore_status = COMPOST_STATUS_INVALID_STATE;
    if (compost_context_snapshot(context, &restore_snapshot) != COMPOST_STATUS_OK ||
        compost_context_metabolic_snapshot(context, &restore_metabolic) != COMPOST_STATUS_OK ||
        compost_create(&config, UINT64_C(12), &restored_context) != COMPOST_STATUS_OK ||
        (restore_status = compost_context_restore_snapshot(
            restored_context, &restore_snapshot, &restore_metabolic
        )) != COMPOST_STATUS_OK ||
        compost_context_state_digest(restored_context) != compost_context_state_digest(context)) {
        (void)fprintf(stderr, "restore status=%d\n", (int)restore_status);
        compost_destroy(restored_context);
        compost_destroy(context);
        return fail("native snapshot restore");
    }
    const uint64_t restored_digest = compost_context_state_digest(restored_context);
    restore_snapshot.abi_version = UINT32_C(2);
    if (compost_context_restore_snapshot(
            restored_context, &restore_snapshot, &restore_metabolic
        ) != COMPOST_STATUS_INVALID_STATE ||
        compost_context_state_digest(restored_context) != restored_digest) {
        compost_destroy(restored_context);
        compost_destroy(context);
        return fail("native snapshot restore transaction");
    }
    if (compost_context_snapshot(restored_context, &restore_snapshot) != COMPOST_STATUS_OK) {
        compost_destroy(restored_context);
        compost_destroy(context);
        return fail("native snapshot restore recapture");
    }
    restore_snapshot.activity.energy_spent = NAN;
    if (compost_context_restore_snapshot(
            restored_context, &restore_snapshot, &restore_metabolic
        ) != COMPOST_STATUS_INVALID_STATE ||
        compost_context_state_digest(restored_context) != restored_digest) {
        compost_destroy(restored_context);
        compost_destroy(context);
        return fail("native snapshot non-finite rejection");
    }
    if (compost_context_snapshot(restored_context, &restore_snapshot) != COMPOST_STATUS_OK) {
        compost_destroy(restored_context);
        compost_destroy(context);
        return fail("native snapshot second recapture");
    }
    restore_snapshot.body.structural_mass += UINT64_C(1);
    if (compost_context_restore_snapshot(
            restored_context, &restore_snapshot, &restore_metabolic
        ) != COMPOST_STATUS_INVALID_STATE ||
        compost_context_state_digest(restored_context) != restored_digest) {
        compost_destroy(restored_context);
        compost_destroy(context);
        return fail("native snapshot mass rejection");
    }
    compost_destroy(restored_context);
    if (compost_create(&config, UINT64_C(15), &lifecycle_context) != COMPOST_STATUS_OK ||
        compost_context_digest(lifecycle_context, &input, &result) != COMPOST_STATUS_OK ||
        compost_context_lifecycle_step(lifecycle_context, &empty_input, &lifecycle_result) != COMPOST_STATUS_OK ||
        compost_context_snapshot(lifecycle_context, &snapshot) != COMPOST_STATUS_OK ||
        compost_context_metabolic_snapshot(lifecycle_context, &metabolic) != COMPOST_STATUS_OK ||
        snapshot.age_in_cycles != UINT64_C(1) ||
        metabolic.steps != UINT64_C(1) ||
        snapshot.current_metabolic_epoch != UINT64_C(1) ||
        !isfinite(snapshot.maintenance_deficit) || snapshot.maintenance_deficit < 0.0 ||
        !isfinite(snapshot.maintenance_deficit_total) || snapshot.maintenance_deficit_total < 0.0 ||
        !isfinite(snapshot.maintenance_paid_total) || snapshot.maintenance_paid_total < 0.0) {
        compost_destroy(lifecycle_context);
        compost_destroy(context);
        return fail("explicit lifecycle-step ABI");
    }
    compost_destroy(lifecycle_context);
    compost_config_t starvation_config = config;
    starvation_config.birth_reserve = 0.0;
    compost_context_t *starvation_context = NULL;
    const uint8_t starvation_food[] = {65U, 66U, 67U, 68U};
    const double starvation_nutrition[] = {1.0, 1.0, 1.0, 1.0};
    const compost_step_input_t starvation_input = {
        starvation_food, starvation_nutrition, sizeof(starvation_food)
    };
    bool reached_dead = false;
    if (compost_create(&starvation_config, UINT64_C(16), &starvation_context) != COMPOST_STATUS_OK ||
        compost_context_lifecycle_step(starvation_context, &starvation_input, &lifecycle_result) != COMPOST_STATUS_OK) {
        compost_destroy(starvation_context);
        compost_destroy(context);
        return fail("lifecycle starvation setup");
    }
    for (size_t epoch = 0U; epoch < 128U; ++epoch) {
        if (lifecycle_result.status_after == COMPOST_LIFECYCLE_DEAD) {
            reached_dead = true;
            break;
        }
        if (compost_context_lifecycle_step(starvation_context, &empty_input, &lifecycle_result) != COMPOST_STATUS_OK) {
            compost_destroy(starvation_context);
            compost_destroy(context);
            return fail("lifecycle starvation transition");
        }
    }
    const uint64_t dead_digest = compost_context_state_digest(starvation_context);
    compost_cycle_result_t dead_result = {0};
    uint64_t dead_executed = UINT64_C(77);
    if (compost_context_run_due_lifecycle(
            starvation_context, UINT64_C(3), &dead_result, &dead_executed
        ) != COMPOST_STATUS_OK || dead_executed != 0U ||
        dead_result.status_after != COMPOST_LIFECYCLE_DEAD ||
        compost_context_state_digest(starvation_context) != dead_digest) {
        compost_destroy(starvation_context);
        compost_destroy(context);
        return fail("native due lifecycle dead no-op");
    }
    if (!reached_dead || compost_context_lifecycle_step(
            starvation_context, &empty_input, &dead_result) != COMPOST_STATUS_OK ||
        dead_result.digestion.consumed_bytes != 0U ||
        dead_result.status_after != COMPOST_LIFECYCLE_DEAD ||
        compost_context_state_digest(starvation_context) != dead_digest) {
        compost_destroy(starvation_context);
        compost_destroy(context);
        return fail("lifecycle dead no-op");
    }
    compost_destroy(starvation_context);
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
    if (compost_context_metabolic_snapshot(child, &metabolic) != COMPOST_STATUS_OK ||
        metabolic.progress != 0U || metabolic.steps != 0U) {
        compost_destroy(child);
        compost_destroy(context);
        return fail("child metabolic reset");
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
    compost_snapshot_t invalid_snapshot = {0};
    invalid_snapshot.organism_id = UINT64_C(91);
    invalid_snapshot.cursor = UINT64_C(37);
    if (compost_context_snapshot(NULL, &invalid_snapshot) != COMPOST_STATUS_INVALID_ARGUMENT ||
        invalid_snapshot.organism_id != UINT64_C(91) ||
        invalid_snapshot.cursor != UINT64_C(37)) {
        return fail("opaque snapshot output preservation");
    }
    compost_step_result_t invalid_result = {0};
    invalid_result.consumed_bytes = SIZE_MAX;
    if (compost_context_digest(context, NULL, &invalid_result) != COMPOST_STATUS_INVALID_ARGUMENT ||
        invalid_result.consumed_bytes != SIZE_MAX) {
        compost_destroy(context);
        return fail("opaque step output preservation");
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
    child = (compost_context_t *)(uintptr_t)UINTPTR_MAX;
    try_plan.candidate_found = true;
    try_plan.child_atom_count = 1U;
    try_result.cross_split_mass = UINT64_C(92);
    if (compost_context_try_divide(NULL, 1U, &child, &try_plan, &try_result) != COMPOST_STATUS_INVALID_ARGUMENT ||
        child != (compost_context_t *)(uintptr_t)UINTPTR_MAX ||
        !try_plan.candidate_found || try_plan.child_atom_count != 1U ||
        try_result.cross_split_mass != UINT64_C(92)) {
        return fail("opaque try-division invalid handle");
    }
    compost_context_t *invalid_local_child = (compost_context_t *)(uintptr_t)UINTPTR_MAX;
    compost_division_result_t invalid_local_result = {0};
    invalid_local_result.cross_split_mass = UINT64_C(93);
    if (compost_context_try_local_reproduction(
            NULL, UINT64_C(1), &invalid_local_child, &invalid_local_result
        ) != COMPOST_STATUS_INVALID_ARGUMENT ||
        invalid_local_child != (compost_context_t *)(uintptr_t)UINTPTR_MAX ||
        invalid_local_result.cross_split_mass != UINT64_C(93)) {
        return fail("opaque local-reproduction invalid handle");
    }
    compost_context_t *invalid_partition_child = (compost_context_t *)(uintptr_t)UINTPTR_MAX;
    compost_division_result_t invalid_partition_result = {0};
    invalid_partition_result.cross_split_mass = UINT64_C(94);
    if (compost_context_partition(
            NULL, UINT64_C(1), NULL, 0U, 1.0,
            &invalid_partition_child, &invalid_partition_result
        ) != COMPOST_STATUS_INVALID_ARGUMENT ||
        invalid_partition_child != (compost_context_t *)(uintptr_t)UINTPTR_MAX ||
        invalid_partition_result.cross_split_mass != UINT64_C(94)) {
        return fail("opaque partition invalid handle");
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
    compost_context_t *rollback_context = NULL;
    compost_context_t *rollback_child = (compost_context_t *)(uintptr_t)UINTPTR_MAX;
    compost_cycle_result_t rollback_cycle = {0};
    compost_division_plan_t rollback_plan = {0};
    compost_division_result_t rollback_division = {0};
    rollback_cycle.digestion.consumed_bytes = SIZE_MAX;
    rollback_plan.candidate_found = true;
    rollback_division.cross_split_mass = UINT64_C(77);
    if (compost_create(&division_config, UINT64_C(40), &rollback_context) != COMPOST_STATUS_OK) {
        return fail("opaque rollback setup");
    }
    if (compost_context_digest(rollback_context, &input, &result) != COMPOST_STATUS_OK) {
        compost_destroy(rollback_context);
        return fail("opaque rollback seed");
    }
    const uint64_t rollback_digest = compost_context_state_digest(rollback_context);
    if (compost_context_step_and_try_divide(
            rollback_context, &input, UINT64_C(40), &rollback_child,
            &rollback_cycle, &rollback_plan, &rollback_division
        ) != COMPOST_STATUS_INVALID_ARGUMENT ||
        rollback_child != (compost_context_t *)(uintptr_t)UINTPTR_MAX ||
        rollback_cycle.digestion.consumed_bytes != SIZE_MAX ||
        !rollback_plan.candidate_found || rollback_division.cross_split_mass != UINT64_C(77) ||
        compost_context_state_digest(rollback_context) != rollback_digest) {
        if (rollback_child != (compost_context_t *)(uintptr_t)UINTPTR_MAX) {
            compost_destroy(rollback_child);
        }
        compost_destroy(rollback_context);
        return fail("opaque step-and-division rollback");
    }
    compost_destroy(rollback_context);

    compost_context_t *local_context = NULL;
    compost_context_t *local_child = (compost_context_t *)(uintptr_t)UINTPTR_MAX;
    compost_division_result_t local_result = {0};
    local_result.cross_split_mass = UINT64_C(91);
    if (compost_create(&division_config, UINT64_C(41), &local_context) != COMPOST_STATUS_OK) {
        return fail("local reproduction no-candidate setup");
    }
    const uint64_t local_digest = compost_context_state_digest(local_context);
    if (compost_context_try_local_reproduction(
            local_context, UINT64_C(42), &local_child, &local_result
        ) != COMPOST_STATUS_OK ||
        local_child != NULL || local_result.cross_split_mass != 0U ||
        compost_context_state_digest(local_context) != local_digest) {
        if (local_child != NULL && local_child != (compost_context_t *)(uintptr_t)UINTPTR_MAX) {
            compost_destroy(local_child);
        }
        compost_destroy(local_context);
        return fail("local reproduction no-candidate transaction");
    }
    compost_destroy(local_context);
    return 0;
}
