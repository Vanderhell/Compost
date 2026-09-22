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
    const uint8_t child_atoms[] = {4U};
    uint64_t initial_digest = 0U;
    uint64_t changed_digest = 0U;
    if (COMPOST_NATIVE_ABI_VERSION != UINT32_C(1) ||
        compost_config_default(&config) != COMPOST_STATUS_OK ||
        compost_create(&config, UINT64_C(12), &context) != COMPOST_STATUS_OK ||
        context == NULL ||
        compost_context_digest(context, &input, &result) != COMPOST_STATUS_OK ||
        result.consumed_bytes != 2U ||
        compost_context_snapshot(context, &snapshot) != COMPOST_STATUS_OK ||
        snapshot.organism_id != UINT64_C(12) || snapshot.cursor != 2U) {
        compost_destroy(context);
        return fail("opaque ABI");
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
    if (compost_context_snapshot(NULL, &snapshot) != COMPOST_STATUS_INVALID_ARGUMENT) {
        return fail("opaque ABI invalid handle");
    }
    return 0;
}
