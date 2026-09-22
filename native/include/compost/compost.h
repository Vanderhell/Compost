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
} compost_config_t;

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
    uint64_t structural_created_mass;
    uint64_t structural_transferred_in;
    uint64_t structural_transferred_out;
} compost_material_flow_t;

typedef struct compost_activity_ledger {
    uint64_t bytes_eaten;
    uint64_t processed_bytes;
    uint64_t rejected_bytes;
    uint64_t resorption_events;
    uint64_t division_events;
    double metabolic_debt;
    double energy_spent;
} compost_activity_ledger_t;

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
    bool initialized;
} compost_organism_t;

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

#ifdef __cplusplus
}
#endif

#endif
