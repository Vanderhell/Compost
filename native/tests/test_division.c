#include "compost/compost.h"

#include <stdio.h>

static int fail(const char *message)
{
    (void)fprintf(stderr, "FAIL: %s\n", message);
    return 1;
}

static void add_atom(compost_organism_t *organism, size_t slot, uint8_t key)
{
    organism->atoms[slot].occupied = true;
    organism->atoms[slot].kind = COMPOST_STRUCTURE_ATOM;
    organism->atoms[slot].left = key;
    organism->atoms[slot].strength = 10.0;
    organism->atoms[slot].maintenance = 0.25;
    organism->atoms[slot].evidence = 1.0;
    organism->atoms[slot].income_rate = 1.0;
    organism->body.atom_count += UINT64_C(1);
}

static int add_edge(
    compost_organism_t *organism,
    compost_structure_kind_t kind,
    size_t slot,
    uint8_t left,
    uint8_t right,
    double strength
)
{
    compost_structure_t *structure = kind == COMPOST_STRUCTURE_RELATION
        ? &organism->relations[slot] : &organism->composites[slot];
    uint64_t mass = 0U;
    if (compost_structural_mass(strength, &mass) != COMPOST_STATUS_OK) return 1;
    structure->occupied = true;
    structure->kind = kind;
    structure->left = left;
    structure->right = right;
    structure->strength = strength;
    structure->maintenance = kind == COMPOST_STRUCTURE_RELATION ? 0.5 : 0.3;
    structure->evidence = 1.0;
    structure->income_rate = 1.0;
    organism->body.structural_mass += mass;
    if (kind == COMPOST_STRUCTURE_RELATION) organism->body.relation_count += UINT64_C(1);
    else organism->body.composite_count += UINT64_C(1);
    organism->material_flow.structural_created_mass += mass;
    return 0;
}

int main(void)
{
    compost_config_t config = {0};
    compost_organism_t parent = {0};
    compost_organism_t child = {0};
    compost_division_result_t result = {0};
    const uint8_t region[] = {1U, 2U};
    if (compost_config_default(&config) != COMPOST_STATUS_OK ||
        compost_organism_init(&parent, &config, NULL, UINT64_C(10)) != COMPOST_STATUS_OK) {
        return fail("setup");
    }
    parent.reserve = 100.0;
    add_atom(&parent, 0U, 1U);
    add_atom(&parent, 1U, 2U);
    add_atom(&parent, 2U, 3U);
    add_atom(&parent, 3U, 4U);
    if (add_edge(&parent, COMPOST_STRUCTURE_RELATION, 0U, 1U, 2U, 8.0) != 0 ||
        add_edge(&parent, COMPOST_STRUCTURE_RELATION, 1U, 3U, 4U, 16.0) != 0 ||
        add_edge(&parent, COMPOST_STRUCTURE_COMPOSITE, 0U, 1U, 2U, 4.0) != 0 ||
        add_edge(&parent, COMPOST_STRUCTURE_RELATION, 2U, 2U, 3U, 8.0) != 0 ||
        compost_organism_verify_material_conservation(&parent) != COMPOST_STATUS_OK) {
        compost_organism_destroy(&parent);
        return fail("seed conservation");
    }
    parent.config.boundary_ratio_limit = 0.5;
    compost_division_plan_t plan = {0};
    if (compost_organism_plan_division(&parent, &plan) != COMPOST_STATUS_OK ||
        !plan.candidate_found || !plan.allowed || plan.child_atom_count != 2U ||
        plan.child_atoms[0] != 1U || plan.child_atoms[1] != 2U ||
        plan.birth_gain <= 0.0 || plan.child_income <= plan.child_maintenance ||
        plan.parent_income <= plan.parent_maintenance) {
        compost_organism_destroy(&parent);
        return fail("division viability plan");
    }
    const uint64_t structural_created_before =
        parent.material_flow.structural_created_mass +
        parent.material_flow.structural_transferred_in;
    uint8_t selected[COMPOST_MAX_ATOMS] = {0};
    size_t selected_count = 0U;
    double selected_ratio = 0.0;
    if (compost_organism_select_partition(&parent, 0.5, selected, COMPOST_MAX_ATOMS,
                                          &selected_count, &selected_ratio) != COMPOST_STATUS_OK ||
        selected_count != 2U || selected[0] != 1U || selected[1] != 2U ||
        selected_ratio < 0.2857 || selected_ratio > 0.2858) {
        compost_organism_destroy(&parent);
        return fail("partition selector");
    }
    if (compost_organism_partition(&parent, &child, UINT64_C(11), region, 2U, 1.0, &result) != COMPOST_STATUS_OK ||
        result.child_structural_mass != UINT64_C(7) || result.cross_split_mass != UINT64_C(4) ||
        result.parent_reserve_after_cost != 99.0 || parent.territory.depth != 1U ||
        parent.territory.path[0] != 0U || child.territory.path[0] != 1U ||
        child.parent_id != UINT64_C(10) || child.reserve != 0.0 ||
        child.body.relation_count != UINT64_C(1) || child.body.composite_count != UINT64_C(1) ||
        parent.gut_count != 1U || parent.material_flow.resorbed_mass != UINT64_C(4) ||
        parent.material_flow.structural_transferred_out != UINT64_C(7) ||
        child.material_flow.structural_transferred_in != UINT64_C(7) ||
        structural_created_before !=
            (parent.body.structural_mass - UINT64_C(256)) +
            (child.body.structural_mass - UINT64_C(256)) +
            parent.material_flow.resorbed_mass ||
        compost_organism_verify_material_conservation(&parent) != COMPOST_STATUS_OK ||
        compost_organism_verify_material_conservation(&child) != COMPOST_STATUS_OK) {
        compost_organism_destroy(&child);
        compost_organism_destroy(&parent);
        return fail("partition transaction");
    }
    compost_organism_destroy(&child);
    compost_organism_destroy(&parent);

    compost_organism_t invalid_parent = {0};
    compost_organism_t invalid_child = {0};
    compost_division_result_t invalid_result = {0};
    const uint8_t duplicate_region[] = {1U, 1U};
    const uint8_t whole_region[] = {1U, 2U};
    if (compost_organism_init(&invalid_parent, &config, NULL, UINT64_C(20)) != COMPOST_STATUS_OK) {
        return fail("invalid setup");
    }
    invalid_parent.reserve = 2.0;
    add_atom(&invalid_parent, 0U, 1U);
    add_atom(&invalid_parent, 1U, 2U);
    const uint64_t before_invalid = compost_organism_state_digest(&invalid_parent);
    if (compost_organism_partition(&invalid_parent, &invalid_child, UINT64_C(21), duplicate_region, 2U, 1.0, &invalid_result) != COMPOST_STATUS_INVALID_ARGUMENT ||
        invalid_child.initialized || compost_organism_state_digest(&invalid_parent) != before_invalid ||
        compost_organism_partition(&invalid_parent, &invalid_child, UINT64_C(21), whole_region, 2U, 1.0, &invalid_result) != COMPOST_STATUS_INVALID_ARGUMENT ||
        invalid_child.initialized || compost_organism_state_digest(&invalid_parent) != before_invalid) {
        compost_organism_destroy(&invalid_parent);
        return fail("transactional invalid partition");
    }
    compost_organism_destroy(&invalid_parent);

    compost_organism_t minimum = {0};
    compost_organism_t minimum_child = {0};
    compost_division_plan_t minimum_plan = {0};
    compost_division_result_t minimum_result = {0};
    const uint8_t minimum_region[] = {7U};
    if (compost_organism_init(&minimum, &config, NULL, UINT64_C(30)) != COMPOST_STATUS_OK) {
        return fail("minimum setup");
    }
    add_atom(&minimum, 0U, 7U);
    if (compost_organism_plan_division(&minimum, &minimum_plan) != COMPOST_STATUS_OK ||
        minimum_plan.candidate_found ||
        compost_organism_partition(&minimum, &minimum_child, UINT64_C(31), minimum_region, 1U,
                                   1.0, &minimum_result) != COMPOST_STATUS_INVALID_ARGUMENT ||
        minimum_child.initialized) {
        compost_organism_destroy(&minimum);
        return fail("minimum body rejection");
    }
    compost_organism_destroy(&minimum);

    compost_organism_t zero_reserve = {0};
    compost_organism_t zero_child = {0};
    const uint8_t zero_region[] = {1U};
    if (compost_organism_init(&zero_reserve, &config, NULL, UINT64_C(40)) != COMPOST_STATUS_OK) {
        return fail("zero reserve setup");
    }
    zero_reserve.reserve = 0.0;
    add_atom(&zero_reserve, 0U, 1U);
    add_atom(&zero_reserve, 1U, 2U);
    const uint64_t zero_before = compost_organism_state_digest(&zero_reserve);
    if (compost_organism_partition(&zero_reserve, &zero_child, UINT64_C(41), zero_region, 1U, 1.0,
                                   &minimum_result) != COMPOST_STATUS_INVALID_ARGUMENT ||
        zero_child.initialized || compost_organism_state_digest(&zero_reserve) != zero_before) {
        compost_organism_destroy(&zero_reserve);
        return fail("zero reserve rollback");
    }
    compost_organism_destroy(&zero_reserve);
    return 0;
}
