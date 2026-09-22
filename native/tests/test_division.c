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
        compost_organism_verify_material_conservation(&parent) != COMPOST_STATUS_OK ||
        compost_organism_verify_material_conservation(&child) != COMPOST_STATUS_OK) {
        compost_organism_destroy(&child);
        compost_organism_destroy(&parent);
        return fail("partition transaction");
    }
    compost_organism_destroy(&child);
    compost_organism_destroy(&parent);
    return 0;
}
