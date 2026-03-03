#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/ioctl.h>
#include <linux/perf_event.h>
#include <asm/unistd.h>
#include <sched.h>
#include <sys/wait.h>
#include <errno.h>
#include <time.h>
#include <fcntl.h>
#include "cJSON.h"
#include "json_utils.h"
/**
 * Compute statistics for an array of values.
 */
void compute_stats(double *arr, int n, double *min, double *max, double *median)
{
    if (n <= 0)
        return;
    *min = *max = arr[0];
    for (int i = 1; i < n; i++)
    {
        if (arr[i] < *min)
            *min = arr[i];
        if (arr[i] > *max)
            *max = arr[i];
    }

    float *sorted = malloc(n * sizeof(double));
    if (!sorted)
    {
        perror("malloc in compute_stats");
        return;
    }

    for (int i = 0; i < n; i++)
        sorted[i] = arr[i];

    // Simple bubble sort
    for (int i = 0; i < n - 1; i++)
        for (int j = 0; j < n - i - 1; j++)
            if (sorted[j] > sorted[j + 1])
            {
                double tmp = sorted[j];
                sorted[j] = sorted[j + 1];
                sorted[j + 1] = tmp;
            }

    if (n % 2 == 0)
        *median = (sorted[n / 2 - 1] + sorted[n / 2]) / 2.0f;
    else
        *median = sorted[n / 2];

    free(sorted);
}

/**
 * Update or add a doubles array inside a sub-JSON object.
 * Example: in {"measurements": {...}}, add or replace "doubles_series".
 */
void update_subjson_double_array(const char *filename, const char *subkey,
                                 const char *array_key, const double *values, int count)
{
    // --- Read file ---
    FILE *f = fopen(filename, "r");
    if (!f)
    {
        perror("Error opening file");
        return;
    }

    fseek(f, 0, SEEK_END);
    long len = ftell(f);
    rewind(f);

    char *data = malloc(len + 1);
    fread(data, 1, len, f);
    data[len] = '\0';
    fclose(f);

    // --- Parse ---
    cJSON *root = cJSON_Parse(data);
    free(data);
    if (!root)
    {
        printf("Error parsing JSON\n");
        return;
    }

    // --- Get or create sub-object ---
    cJSON *sub = cJSON_GetObjectItem(root, subkey);
    if (!sub)
    {
        sub = cJSON_CreateObject();
        cJSON_AddItemToObject(root, subkey, sub);
    }

    // --- Create array of doubles ---
    cJSON *arr = cJSON_CreateArray();
    for (int i = 0; i < count; i++)
        cJSON_AddItemToArray(arr, cJSON_CreateNumber(values[i]));

    // --- Add or replace inside sub-object ---
    cJSON *existing = cJSON_GetObjectItem(sub, array_key);
    if (existing)
        cJSON_ReplaceItemInObject(sub, array_key, arr);
    else
        cJSON_AddItemToObject(sub, array_key, arr);

    // --- Write back to file ---
    char *out = cJSON_Print(root);
    f = fopen(filename, "w");
    if (f)
    {
        fputs(out, f);
        fclose(f);
        // printf("Updated '%s.%s' with %d doubles in %s\n", subkey, array_key, count, filename);
    }
    else
        perror("Error writing file");

    // --- Cleanup ---
    free(out);
    cJSON_Delete(root);
}

/**
 * Build experiment name including all parameters from the simulation struct.
 *
 * Format: "<nthreads>_<seq_fraction>_<nbarriers>_<total_units_per_barrier>"
 */
char *build_name(const parallel_sim_params_t *sim)
{
    if (!sim)
        return NULL;

    size_t len = snprintf(
                     NULL,
                     0,
                     "%d_%.2f_%d_%llu",
                     sim->nthreads,
                     sim->seq_fraction,
                     sim->nbarriers,
                     (unsigned long long)sim->total_units_per_barrier) +
                 1;

    char *exp_name = malloc(len);
    if (!exp_name)
    {
        perror("malloc");
        return NULL;
    }

    snprintf(
        exp_name,
        len,
        "%d_%.2f_%d_%llu",
        sim->nthreads,
        sim->seq_fraction,
        sim->nbarriers,
        (unsigned long long)sim->total_units_per_barrier);

    return exp_name;
}

char *build_json_path(const char *output_json, const char *suffix)
{
    if (!output_json)
    {
        fprintf(stderr, "Error: output_json path not provided\n");
        return NULL;
    }

    size_t len = strlen(output_json) + strlen(suffix) + strlen(".json") + 1;
    char *path = malloc(len);
    if (!path)
    {
        perror("malloc");
        return NULL;
    }

    snprintf(path, len, "%s%s.json", output_json, suffix);
    return path;
}

/**
 * Read an integer array from JSON, handling both single values and arrays.
 * Returns the number of elements read, or -1 on error.
 */
int read_int_array_from_json(cJSON *params, const char *key, int **values_out)
{
    cJSON *item = cJSON_GetObjectItem(params, key);
    if (!item)
        return 0;

    if (item->type == cJSON_Array)
    {
        int count = cJSON_GetArraySize(item);
        int *values = malloc(count * sizeof(int));
        if (!values)
            return -1;

        for (int i = 0; i < count; i++)
        {
            cJSON *elem = cJSON_GetArrayItem(item, i);
            if (elem && elem->type == cJSON_Number)
                values[i] = elem->valueint;
            else
            {
                free(values);
                return -1;
            }
        }
        *values_out = values;
        return count;
    }
    else if (item->type == cJSON_Number)
    {
        // Single value - convert to array
        int *values = malloc(sizeof(int));
        if (!values)
            return -1;
        values[0] = item->valueint;
        *values_out = values;
        return 1;
    }
    return -1;
}
/**
 * Read a double array from JSON, handling both single values and arrays.
 * Returns the number of elements read, or -1 on error.
 */
int read_double_array_from_json(cJSON *params, const char *key, double **values_out)
{
    cJSON *item = cJSON_GetObjectItem(params, key);
    if (!item)
        return 0;

    if (item->type == cJSON_Array)
    {
        int count = cJSON_GetArraySize(item);
        double *values = malloc(count * sizeof(double));
        if (!values)
            return -1;

        for (int i = 0; i < count; i++)
        {
            cJSON *elem = cJSON_GetArrayItem(item, i);
            if (elem && elem->type == cJSON_Number)
                values[i] = elem->valuedouble;
            else
            {
                free(values);
                return -1;
            }
        }
        *values_out = values;
        return count;
    }
    else if (item->type == cJSON_Number)
    {
        // Single value - convert to array
        double *values = malloc(sizeof(double));
        if (!values)
            return -1;
        values[0] = item->valuedouble;
        *values_out = values;
        return 1;
    }
    return -1;
}
int read_params_from_json(const char *filename, params_t *p)
{

    FILE *f = fopen(filename, "rb");
    if (!f)
    {
        fprintf(stderr, "File %s doesnt exits\n", filename);
        return -1;
    }

    fseek(f, 0, SEEK_END);
    long size = ftell(f);
    rewind(f);
    char *buf = malloc(size + 1);
    fread(buf, 1, size, f);
    buf[size] = '\0';
    fclose(f);

    cJSON *json = cJSON_Parse(buf);
    if (!json)
        return -2;

    cJSON *params = cJSON_GetObjectItem(json, "params");
    if (!params)
        return -3;

    const cJSON *arch = cJSON_GetObjectItem(params, "arch");
    const cJSON *sensor = cJSON_GetObjectItem(params, "sensor");
    if (arch && arch->valuestring)
    {
        strncpy(p->arch, arch->valuestring, sizeof(p->arch) - 1);
        p->arch[sizeof(p->arch) - 1] = '\0';
    }
    if (sensor && sensor->valuestring)
    {
        strncpy(p->sensor, sensor->valuestring, sizeof(p->sensor) - 1);
        p->sensor[sizeof(p->sensor) - 1] = '\0';
    }

    p->freq = cJSON_GetObjectItem(params, "freq")->valuedouble;
    p->total_operations = cJSON_GetObjectItem(params, "n_work")->valueint;
    p->n_stat = cJSON_GetObjectItem(params, "n_stat")->valueint;
    p->n_cores = cJSON_GetObjectItem(params, "n_cores") ? cJSON_GetObjectItem(params, "n_cores")->valueint : 8;                     // Default to 8 if not specified
    p->seq_fraction = cJSON_GetObjectItem(params, "seq_fraction") ? cJSON_GetObjectItem(params, "seq_fraction")->valuedouble : 0.0; // Default to 0.0 if not specified
    free(buf);
    cJSON_Delete(json);
    return 0;
}

int create_output_json(const char *filename, const params_t *p,
                       const int *n_cores_array, int n_cores_count,
                       const float *seq_fraction_array, int seq_fraction_count)
{
    cJSON *root = cJSON_CreateObject();
    cJSON *params = cJSON_CreateObject();

    time_t now = time(NULL);
    struct tm tm_now;
    localtime_r(&now, &tm_now);

    char date_str[32];
    strftime(date_str, sizeof(date_str), "%Y-%m-%d %H:%M:%S", &tm_now);
    cJSON_AddStringToObject(params, "date", date_str);
    cJSON_AddStringToObject(params, "arch", p->arch);
    cJSON_AddStringToObject(params, "sensor", p->sensor);
    cJSON_AddNumberToObject(params, "freq", p->freq);
    cJSON_AddNumberToObject(params, "n_work", p->total_operations);
    cJSON_AddNumberToObject(params, "n_stat", p->n_stat);

    // Add n_cores as array if multiple values, otherwise as single value
    // If arrays are provided, use them; otherwise fall back to params_t values
    if (n_cores_array != NULL && n_cores_count > 0)
    {
        if (n_cores_count > 1)
        {
            cJSON *n_cores_json = cJSON_CreateIntArray(n_cores_array, n_cores_count);
            cJSON_AddItemToObject(params, "n_cores", n_cores_json);
        }
        else
        {
            cJSON_AddNumberToObject(params, "n_cores", n_cores_array[0]);
        }
    }
    else
    {
        // Backward compatibility: use single value from params_t
        cJSON_AddNumberToObject(params, "n_cores", p->n_cores);
    }

    // Add seq_fraction as array if multiple values, otherwise as single value
    if (seq_fraction_array != NULL && seq_fraction_count > 0)
    {
        if (seq_fraction_count > 1)
        {
            cJSON *seq_fraction_json = cJSON_CreateFloatArray(seq_fraction_array, seq_fraction_count);
            cJSON_AddItemToObject(params, "seq_fraction", seq_fraction_json);
        }
        else
        {
            cJSON_AddNumberToObject(params, "seq_fraction", seq_fraction_array[0]);
        }
    }
    else
    {
        // Backward compatibility: use single value from params_t
        cJSON_AddNumberToObject(params, "seq_fraction", p->seq_fraction);
    }

    cJSON_AddItemToObject(root, "params", params);
    cJSON_AddItemToObject(root, "energy", cJSON_CreateObject());
    cJSON_AddItemToObject(root, "time", cJSON_CreateObject());
    cJSON_AddItemToObject(root, "temperature", cJSON_CreateObject());
    cJSON_AddItemToObject(root, "voltage", cJSON_CreateObject());

    char *out = cJSON_Print(root);
    FILE *f = fopen(filename, "w");
    if (!f)
        return -1;
    fputs(out, f);
    fclose(f);
    free(out);
    cJSON_Delete(root);
    return 0;
}

/* void set_fixed_frequency(double freq_ghz) {
    char cmd[128];
    snprintf(cmd, sizeof(cmd),
             "sudo-g5k cpupower frequency-set -f %.2fGHz", freq_ghz);
    system(cmd);
} */