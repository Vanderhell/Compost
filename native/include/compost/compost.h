#ifndef COMPOST_COMPOST_H
#define COMPOST_COMPOST_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define COMPOST_NATIVE_ABI_VERSION UINT32_C(1)
#define COMPOST_MAX_TERRITORY_DEPTH 64U
#define COMPOST_MAX_ATOMS 256U
#define COMPOST_MAX_RELATIONS 512U
#define COMPOST_MAX_COMPOSITES 512U
#define COMPOST_MAX_GUT_CHUNKS 128U

typedef enum compost_status {
    COMPOST_STATUS_OK = 0,
    COMPOST_STATUS_INVALID_ARGUMENT = 1,
    COMPOST_STATUS_INVALID_STATE = 2,
    COMPOST_STATUS_OUT_OF_MEMORY = 3,
    COMPOST_STATUS_BUFFER_TOO_SMALL = 4
} compost_status_t;

typedef void *(*compost_allocate_fn)(void *context, size_t size);
typedef void (*compost_deallocate_fn)(void *context, void *memory);

typedef struct compost_allocator {
    void *context;
    compost_allocate_fn allocate;
    compost_deallocate_fn deallocate;
} compost_allocator_t;

typedef struct compost_config {
    uint32_t abi_version;
    uint64_t seed;
    uint64_t max_body_mass;
    uint32_t max_territory_depth;
    double income_decay;
    double atom_income;
    double relation_income;
    double atom_maintenance;
    double relation_maintenance;
    double atom_formation_cost;
    double relation_formation_cost;
} compost_config_t;

typedef enum compost_structure_kind {
    COMPOST_STRUCTURE_ATOM = 0,
    COMPOST_STRUCTURE_RELATION = 1,
    COMPOST_STRUCTURE_COMPOSITE = 2
} compost_structure_kind_t;

typedef struct compost_structure {
    bool occupied;
    compost_structure_kind_t kind;
    uint8_t left;
    uint8_t right;
    double strength;
    double maintenance;
    double evidence;
    double income_rate;
} compost_structure_t;

typedef enum compost_material_origin {
    COMPOST_MATERIAL_EXTERNAL = 0,
    COMPOST_MATERIAL_RESORPTION = 1
} compost_material_origin_t;

typedef struct compost_gut_chunk {
    uint64_t mass;
    compost_material_origin_t origin;
} compost_gut_chunk_t;

typedef struct compost_body {
    uint64_t structural_mass;
    uint64_t atom_count;
    uint64_t relation_count;
    uint64_t composite_count;
} compost_body_t;

typedef struct compost_material_flow {
    uint64_t input_mass;
    uint64_t assimilated_mass;
    uint64_t rejected_mass;
    uint64_t resorbed_mass;
    uint64_t processed_mass;
    uint64_t expelled_mass;
    uint64_t external_expelled_mass;
    uint64_t resorption_expelled_mass;
    uint64_t structural_created_mass;
    uint64_t structural_transferred_in;
    uint64_t structural_transferred_out;
} compost_material_flow_t;

typedef struct compost_activity_costs {
    double byte;
    double digest_per_kib;
    double reject_per_kib;
    double resorption_per_kib;
    double relation_created;
    double relation_strengthened;
    double composite_created;
    double composite_strengthened;
    double structural_mass_delta;
    double resorption;
    double division;
    double basal_mass;
    double settlement_base;
    double settlement_mass_scale;
} compost_activity_costs_t;

typedef struct compost_activity_counters {
    uint64_t bytes_eaten;
    uint64_t relations_created;
    uint64_t relations_strengthened;
    uint64_t composites_created;
    uint64_t composites_strengthened;
    uint64_t structural_mass_added;
    uint64_t structural_mass_lost;
    uint64_t resorption_events;
    uint64_t division_events;
    uint64_t processed_bytes;
    uint64_t rejected_bytes;
    uint64_t resorbed_processed_bytes;
} compost_activity_counters_t;

typedef struct compost_activity_ledger {
    double metabolic_debt;
    double energy_spent;
    uint64_t settlements;
    compost_activity_counters_t counters;
} compost_activity_ledger_t;

typedef struct compost_forgetting_delta {
    double strength_after;
    double income_rate_after;
} compost_forgetting_delta_t;

typedef struct compost_territory {
    uint8_t path[COMPOST_MAX_TERRITORY_DEPTH];
    uint32_t depth;
    uint64_t organism_id;
    uint64_t local_birth_counter;
    bool alive;
} compost_territory_t;

typedef enum compost_lifecycle_status {
    COMPOST_LIFECYCLE_ALIVE = 0,
    COMPOST_LIFECYCLE_DEAD = 1
} compost_lifecycle_status_t;

typedef struct compost_snapshot {
    uint32_t abi_version;
    uint64_t organism_id;
    uint64_t parent_id;
    bool has_parent;
    uint64_t generation;
    uint64_t cursor;
    uint64_t age_in_cycles;
    compost_lifecycle_status_t status;
    double reserve;
    compost_body_t body;
    compost_material_flow_t material_flow;
    compost_activity_ledger_t activity;
    compost_territory_t territory;
    compost_structure_t atoms[COMPOST_MAX_ATOMS];
    compost_structure_t relations[COMPOST_MAX_RELATIONS];
    compost_structure_t composites[COMPOST_MAX_COMPOSITES];
    uint64_t activated_receptors[4];
    compost_gut_chunk_t gut[COMPOST_MAX_GUT_CHUNKS];
    uint32_t gut_head;
    uint32_t gut_count;
} compost_snapshot_t;

typedef struct compost_organism {
    compost_allocator_t allocator;
    compost_config_t config;
    uint64_t organism_id;
    uint64_t parent_id;
    bool has_parent;
    uint64_t generation;
    uint64_t cursor;
    uint64_t age_in_cycles;
    compost_lifecycle_status_t status;
    double reserve;
    compost_body_t body;
    compost_material_flow_t material_flow;
    compost_activity_ledger_t activity;
    compost_territory_t territory;
    compost_structure_t atoms[COMPOST_MAX_ATOMS];
    compost_structure_t relations[COMPOST_MAX_RELATIONS];
    compost_structure_t composites[COMPOST_MAX_COMPOSITES];
    uint64_t activated_receptors[4];
    compost_gut_chunk_t gut[COMPOST_MAX_GUT_CHUNKS];
    uint32_t gut_head;
    uint32_t gut_count;
    bool initialized;
} compost_organism_t;

typedef struct compost_step_input {
    const uint8_t *food;
    const double *nutrition;
    size_t length;
} compost_step_input_t;

typedef struct compost_step_result {
    size_t consumed_bytes;
    uint64_t assimilated_mass;
    uint64_t rejected_mass;
    uint64_t relations_created;
    uint64_t relations_strengthened;
} compost_step_result_t;

typedef struct compost_maintenance_result {
    double required;
    double paid;
    double deficit;
    uint64_t weakened_candidates;
    uint64_t resorbed_mass;
} compost_maintenance_result_t;

/* A zeroed allocator selects the library's malloc/free-backed defaults. */
compost_status_t compost_config_default(compost_config_t *config);

/* Initializes an organism. The destination must not be initialized already. */
compost_status_t compost_organism_init(
    compost_organism_t *organism,
    const compost_config_t *config,
    const compost_allocator_t *allocator,
    uint64_t organism_id
);

/* Releases owned resources and returns the object to its zero state. */
void compost_organism_destroy(compost_organism_t *organism);

/* Copies the current behavioral scalar state into snapshot. */
compost_status_t compost_organism_snapshot(
    const compost_organism_t *organism,
    compost_snapshot_t *snapshot
);

const char *compost_status_name(compost_status_t status);

/* Pure rule. Finite strength is required; negative strength returns mass zero. */
compost_status_t compost_structural_mass(double strength, uint64_t *mass);

/* Copies counters into the ledger and adds the exact Python reference cost. */
compost_status_t compost_activity_ledger_add(
    compost_activity_ledger_t *ledger,
    const compost_activity_counters_t *counters,
    uint64_t body_mass,
    const compost_activity_costs_t *costs
);

compost_status_t compost_activity_settlement_threshold(
    uint64_t body_mass,
    const compost_activity_costs_t *costs,
    double *threshold
);

compost_status_t compost_activity_basal_cost(
    uint64_t body_mass,
    const compost_activity_costs_t *costs,
    double *cost
);

compost_status_t compost_forgetting_delta(
    double strength,
    double income_rate,
    double maintenance,
    double income_decay,
    compost_forgetting_delta_t *delta
);

/* Returns zero for no deficit and at least one for every positive deficit. */
compost_status_t compost_maintenance_weakening_budget(
    double maintenance_deficit,
    uint64_t body_mass,
    uint64_t *budget
);

/*
 * Deterministic byte digestion checkpoint. The environment owns input memory;
 * the function never retains food pointers and performs no I/O. It mutates
 * structural state and reserve but does not yet run the full maintenance,
 * gut, division, or death tail of a logical lifecycle step.
 */
compost_status_t compost_organism_digest(
    compost_organism_t *organism,
    const compost_step_input_t *input,
    compost_step_result_t *result
);

/* Applies the eager reference maintenance/forgetting slice and advances age. */
compost_status_t compost_organism_maintenance(
    compost_organism_t *organism,
    compost_maintenance_result_t *result
);

compost_status_t compost_organism_enqueue_resorbed(
    compost_organism_t *organism,
    uint64_t mass
);

compost_status_t compost_organism_process_resorption(
    compost_organism_t *organism,
    uint64_t capacity,
    uint64_t *processed
);

#ifdef __cplusplus
}
#endif

#endif
