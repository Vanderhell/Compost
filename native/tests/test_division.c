#include "compost/compost.h"

#include <stdlib.h>
#include <stdio.h>
#include <string.h>

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
    parent.config.reproduction_minimum_body = 4U;
    uint8_t local_child_atoms[COMPOST_MAX_ATOMS] = {0U};
    size_t local_child_count = 0U;
    if (compost_organism_select_local_reproduction(
            &parent, local_child_atoms, COMPOST_MAX_ATOMS, &local_child_count
        ) != COMPOST_STATUS_OK || local_child_count != 3U ||
        local_child_atoms[0] != 2U || local_child_atoms[1] != 3U ||
        local_child_atoms[2] != 4U) {
        compost_organism_destroy(&parent);
        return fail("local reproduction selector");
    }
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
    const uint64_t child_created_before =
        child.material_flow.structural_created_mass +
        child.material_flow.structural_transferred_in;
    compost_organism_t grandchild = {0};
    compost_division_result_t grandchild_result = {0};
    const uint8_t nested_region[] = {1U};
    if (compost_organism_partition(
            &child, &grandchild, UINT64_MAX, nested_region, 1U, 0.0, &grandchild_result
        ) != COMPOST_STATUS_OK ||
        grandchild.organism_id != UINT64_MAX || grandchild.parent_id != UINT64_C(11) ||
        grandchild.generation != UINT64_C(2) ||
        grandchild.territory.depth != 2U || grandchild.territory.path[0] != UINT8_C(1) ||
        grandchild.territory.path[1] != UINT8_C(1) || child.territory.path[1] != UINT8_C(0) ||
        child.body.atom_count != UINT64_C(1) || grandchild.body.atom_count != UINT64_C(1) ||
        child_created_before !=
            (child.body.structural_mass - UINT64_C(256)) +
            (grandchild.body.structural_mass - UINT64_C(256)) +
            child.material_flow.resorbed_mass ||
        compost_organism_verify_material_conservation(&child) != COMPOST_STATUS_OK ||
        compost_organism_verify_material_conservation(&grandchild) != COMPOST_STATUS_OK) {
        compost_organism_destroy(&grandchild);
        compost_organism_destroy(&child);
        compost_organism_destroy(&parent);
        return fail("nested partition transaction");
    }
    compost_organism_destroy(&grandchild);
    compost_organism_destroy(&child);
    compost_organism_destroy(&parent);

    compost_organism_t dense = {0};
    compost_organism_t dense_child = {0};
    compost_division_result_t dense_result = {0};
    const uint8_t dense_region[] = {10U, 11U, 12U, 13U};
    if (compost_organism_init(&dense, &config, NULL, UINT64_C(50)) != COMPOST_STATUS_OK) {
        return fail("dense setup");
    }
    dense.reserve = 100.0;
    for (size_t index = 0U; index < 8U; ++index) {
        add_atom(&dense, index, (uint8_t)(10U + index));
    }
    if (add_edge(&dense, COMPOST_STRUCTURE_RELATION, 0U, 10U, 11U, 8.0) != 0 ||
        add_edge(&dense, COMPOST_STRUCTURE_RELATION, 1U, 11U, 12U, 8.0) != 0 ||
        add_edge(&dense, COMPOST_STRUCTURE_RELATION, 2U, 12U, 13U, 8.0) != 0 ||
        add_edge(&dense, COMPOST_STRUCTURE_RELATION, 3U, 13U, 14U, 4.0) != 0 ||
        add_edge(&dense, COMPOST_STRUCTURE_RELATION, 4U, 11U, 15U, 4.0) != 0 ||
        add_edge(&dense, COMPOST_STRUCTURE_COMPOSITE, 0U, 10U, 11U, 4.0) != 0 ||
        add_edge(&dense, COMPOST_STRUCTURE_COMPOSITE, 1U, 12U, 13U, 4.0) != 0 ||
        add_edge(&dense, COMPOST_STRUCTURE_COMPOSITE, 2U, 13U, 14U, 4.0) != 0 ||
        add_edge(&dense, COMPOST_STRUCTURE_COMPOSITE, 3U, 15U, 16U, 4.0) != 0 ||
        add_edge(&dense, COMPOST_STRUCTURE_COMPOSITE, 4U, 16U, 17U, 4.0) != 0 ||
        compost_organism_verify_material_conservation(&dense) != COMPOST_STATUS_OK) {
        compost_organism_destroy(&dense);
        return fail("dense seed conservation");
    }
    const uint64_t dense_created_before =
        dense.material_flow.structural_created_mass + dense.material_flow.structural_transferred_in;
    if (compost_organism_partition(
            &dense, &dense_child, UINT64_C(51), dense_region, 4U, 1.0, &dense_result
        ) != COMPOST_STATUS_OK ||
        dense.body.atom_count != UINT64_C(4) || dense_child.body.atom_count != UINT64_C(4) ||
        dense.gut_count == 0U || dense.material_flow.resorbed_mass == 0U ||
        dense_created_before !=
            (dense.body.structural_mass - UINT64_C(256)) +
            (dense_child.body.structural_mass - UINT64_C(256)) +
            dense.material_flow.resorbed_mass ||
        compost_organism_verify_material_conservation(&dense) != COMPOST_STATUS_OK ||
        compost_organism_verify_material_conservation(&dense_child) != COMPOST_STATUS_OK) {
        compost_organism_destroy(&dense_child);
        compost_organism_destroy(&dense);
        return fail("dense partition conservation");
    }
    compost_organism_destroy(&dense_child);
    compost_organism_destroy(&dense);

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

    for (uint64_t case_id = 0U; case_id < UINT64_C(32); ++case_id) {
        static compost_organism_t campaign_parent;
        static compost_organism_t campaign_child;
        compost_division_result_t campaign_result = {0};
        memset(&campaign_parent, 0, sizeof(campaign_parent));
        memset(&campaign_child, 0, sizeof(campaign_child));
        const size_t atom_count = (size_t)(4U + (case_id % UINT64_C(5)));
        if (compost_organism_init(&campaign_parent, &config, NULL,
                                  UINT64_C(100) + case_id) != COMPOST_STATUS_OK) {
            return fail("campaign setup");
        }
        campaign_parent.reserve = 10000.0;
        for (size_t index = 0U; index < atom_count; ++index) {
            add_atom(&campaign_parent, index, (uint8_t)(20U + index));
        }
        for (size_t index = 0U; index + 1U < atom_count; ++index) {
            const compost_structure_kind_t kind =
                ((case_id + (uint64_t)index) % UINT64_C(3)) == 0U
                    ? COMPOST_STRUCTURE_COMPOSITE : COMPOST_STRUCTURE_RELATION;
            if (add_edge(&campaign_parent, kind, index,
                         (uint8_t)(20U + index), (uint8_t)(21U + index),
                         4.0 + (double)((case_id + (uint64_t)index) % UINT64_C(13))) != 0) {
                compost_organism_destroy(&campaign_parent);
                return fail("campaign edge setup");
            }
        }
        if (atom_count > 4U && add_edge(
                &campaign_parent, COMPOST_STRUCTURE_RELATION, atom_count,
                20U, (uint8_t)(20U + atom_count - 1U), 16.0) != 0) {
            compost_organism_destroy(&campaign_parent);
            return fail("campaign cross-edge setup");
        }
        if (compost_organism_verify_material_conservation(&campaign_parent) != COMPOST_STATUS_OK) {
            compost_organism_destroy(&campaign_parent);
            return fail("campaign seed conservation");
        }
        const uint64_t created_before =
            campaign_parent.material_flow.structural_created_mass +
            campaign_parent.material_flow.structural_transferred_in;
        uint8_t selected_campaign[COMPOST_MAX_ATOMS] = {0};
        const size_t selected_campaign_count = atom_count / 2U;
        for (size_t index = 0U; index < selected_campaign_count; ++index) {
            selected_campaign[index] = (uint8_t)(20U + index);
        }
        if (compost_organism_partition(
                &campaign_parent, &campaign_child, UINT64_C(1000) + case_id,
                selected_campaign, selected_campaign_count, 1.0, &campaign_result
            ) != COMPOST_STATUS_OK ||
            created_before !=
                (campaign_parent.body.structural_mass - UINT64_C(256)) +
                (campaign_child.body.structural_mass - UINT64_C(256)) +
                campaign_parent.material_flow.resorbed_mass ||
            compost_organism_verify_material_conservation(&campaign_parent) != COMPOST_STATUS_OK ||
            compost_organism_verify_material_conservation(&campaign_child) != COMPOST_STATUS_OK) {
            compost_organism_destroy(&campaign_child);
            compost_organism_destroy(&campaign_parent);
            return fail("campaign partition conservation");
        }
        compost_organism_destroy(&campaign_child);
        compost_organism_destroy(&campaign_parent);
    }

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

    compost_organism_t *isolated = calloc(1U, sizeof(*isolated));
    uint8_t isolated_atoms[COMPOST_MAX_ATOMS] = {0U};
    size_t isolated_count = 99U;
    if (isolated == NULL || compost_organism_init(isolated, &config, NULL, UINT64_C(60)) != COMPOST_STATUS_OK) {
        free(isolated);
        return fail("isolated setup");
    }
    isolated->reserve = 100.0;
    isolated->config.reproduction_minimum_body = 1U;
    for (size_t index = 0U; index < COMPOST_MAX_ATOMS; ++index) {
        add_atom(isolated, index, (uint8_t)index);
    }
    if (compost_organism_select_local_reproduction(
            isolated, isolated_atoms, COMPOST_MAX_ATOMS, &isolated_count
        ) != COMPOST_STATUS_INVALID_STATE || isolated_count != 0U) {
        compost_organism_destroy(isolated);
        free(isolated);
        return fail("maximum isolated local reproduction");
    }
    compost_organism_destroy(isolated);
    free(isolated);
    return 0;
}
