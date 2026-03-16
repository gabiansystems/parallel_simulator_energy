/**
 * json_utils.h
 *
 * Utilities for creating and updating the JSON output file
 * used by the parallel simulation measurements.
 */

#ifndef JSON_UTILS_H
#define JSON_UTILS_H

#include "parallel_sim.h"

/**
 * Parameters describing a measurement experiment.
 *
 * This definition MUST stay in sync with the implementation in
 * `json_utils.c`. It uses fixed-size buffers for strings so the
 * implementation can safely copy JSON strings into them.
 */
typedef struct
{
    int arch;          /**< Architecture identifier for RAPL */
    int sensor;        /**< RAPL domain. */
    double freq;            /**< Target CPU frequency in GHz. */
    int total_operations;   /**< Total synthetic work units per run. */
    int n_stat;             /**< Number of repetitions / statistical samples. */
    int n_cores;            /**< Default core count if arrays are not provided. */
    float seq_fraction;     /**< Default sequential fraction if arrays are not provided. */
} params_t;

/**
 * Create and initialize the main JSON output file.
 *
 * @param output_file         Path (or base name) of the JSON file to create
 * @param params              Global experiment parameters
 * @param n_cores_array       Array of core counts
 * @param n_cores_count       Number of elements in n_cores_array
 * @param seq_fraction_array  Array of sequential fractions
 * @param seq_fraction_count  Number of elements in seq_fraction_array
 *
 * @return 0 on success, non‑zero on error
 */
int create_output_json(const char *output_file,
                       const params_t *params,
                       const int *n_cores_array,
                       int n_cores_count,
                       const float *seq_fraction_array,
                       int seq_fraction_count);

/**
 * Append or update a sub‑JSON array of doubles for a given experiment.
 *
 * @param output_file  JSON file to update
 * @param key          Top‑level key (e.g., "energy", "time")
 * @param exp_name     Name of the experiment/series
 * @param values       Array of double values
 * @param count        Number of elements in values
 *
 * @return 0 on success, non‑zero on error
 */
void update_subjson_double_array(const char *output_file,
                                 const char *key,
                                 const char *exp_name,
                                 const double *values,
                                 int count);

/**
 * Read experiment parameters from a JSON configuration file.
 *
 * Expects a top-level "params" object with at least:
 *  - arch (string)
 *  - sensor (string)
 *  - freq (number, GHz)
 *  - n_work (integer)
 *  - n_stat (integer)
 *  - n_cores (integer)
 *  - seq_fraction (number, percent 0–100)
 */
int read_params_from_json(const char *filename, params_t *p);

/**
 * Build a human-readable experiment name from simulation parameters.
 *
 * The returned string is heap-allocated and must be freed by the caller.
 */
char *build_name(const parallel_sim_params_t *sim);

#endif /* JSON_UTILS_H */

