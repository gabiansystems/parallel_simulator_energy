#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <dirent.h>
#include "cJSON.h"
#include "json_utils.h"

/* ── RAPL sysfs ──────────────────────────────────────────────────────────── */

const char *find_rapl_pmu_dir(void)
{
    static char found[320];
    static const char *prefixes[] = { "power", "intel-rapl", NULL };
    const char *base = "/sys/bus/event_source/devices";

    DIR *d = opendir(base);
    if (!d) return NULL;

    struct dirent *e;
    while ((e = readdir(d)) != NULL) {
        for (int i = 0; prefixes[i]; i++) {
            if (strncmp(e->d_name, prefixes[i], strlen(prefixes[i])) != 0)
                continue;
            char type_path[320];
            snprintf(type_path, sizeof(type_path), "%s/%s/type", base, e->d_name);
            FILE *f = fopen(type_path, "r");
            if (!f) continue;
            int val = -1;
            int ok = fscanf(f, "%d", &val) == 1 && val > 0;
            fclose(f);
            if (!ok) continue;
            snprintf(found, sizeof(found), "%s/%s", base, e->d_name);
            closedir(d);
            return found;
        }
    }
    closedir(d);
    return NULL;
}

double read_rapl_pkg_energy_scale(double fallback_j_per_count)
{
    const char *dir = find_rapl_pmu_dir();
    if (!dir) {
        fprintf(stderr, "[WARN] no RAPL PMU dir — scale falls back to %.3e J/count\n",
                fallback_j_per_count);
        return fallback_j_per_count;
    }
    char path[384];
    snprintf(path, sizeof(path), "%s/events/energy-pkg.scale", dir);
    FILE *f = fopen(path, "r");
    if (!f) return fallback_j_per_count;
    double scale = -1.0;
    int ok = fscanf(f, "%lf", &scale) == 1 && scale > 0.0;
    fclose(f);
    return ok ? scale : fallback_j_per_count;
}

int get_rapl_type(const char *arch)
{
    const char *dir = find_rapl_pmu_dir();
    if (dir) {
        char type_path[320];
        snprintf(type_path, sizeof(type_path), "%s/type", dir);
        FILE *f = fopen(type_path, "r");
        if (f) {
            int val = -1;
            if (fscanf(f, "%d", &val) == 1 && val > 0) {
                fclose(f);
                printf("[RAPL] PMU type=%d (from %s)\n", val, dir);
                return val;
            }
            fclose(f);
        }
    }
    /* Fallback table */
    if (strcmp(arch, "SNB") == 0) return 27;
    if (strcmp(arch, "IVB") == 0) return 29;
    if (strcmp(arch, "HSW") == 0) return 34;
    if (strcmp(arch, "BDW") == 0) return 33;
    if (strcmp(arch, "SKL") == 0) return 53;
    if (strcmp(arch, "CLX") == 0) return 65;
    if (strcmp(arch, "ICX") == 0) return 89;
    if (strcmp(arch, "SPR") == 0) return 106;
    if (strcmp(arch, "EMR") == 0) return 175;
    fprintf(stderr, "[RAPL] no sysfs PMU and arch '%s' unknown — using HSW default\n", arch);
    return 34;
}

int get_rapl_config(const char *sensor)
{
    if (strcmp(sensor, "PKG")  == 0) return 2;
    if (strcmp(sensor, "PP0")  == 0) return 1;
    if (strcmp(sensor, "PP1")  == 0) return 4;
    if (strcmp(sensor, "DRAM") == 0) return 8;
    return 2;
}

/* ── JSON I/O ────────────────────────────────────────────────────────────── */

int read_params_from_json(const char *filename, params_t *p)
{
    FILE *f = fopen(filename, "rb");
    if (!f) { fprintf(stderr, "File not found: %s\n", filename); return -1; }
    fseek(f, 0, SEEK_END); long sz = ftell(f); rewind(f);
    char *buf = malloc(sz + 1);
    fread(buf, 1, sz, f); buf[sz] = '\0'; fclose(f);

    cJSON *json = cJSON_Parse(buf); free(buf);
    if (!json) return -2;

    cJSON *params = cJSON_GetObjectItem(json, "params");
    if (!params) { cJSON_Delete(json); return -3; }

    cJSON *arch   = cJSON_GetObjectItem(params, "arch");
    cJSON *sensor = cJSON_GetObjectItem(params, "sensor");
    cJSON *vendor = cJSON_GetObjectItem(params, "vendor");

    if (arch   && arch->valuestring)   p->arch   = get_rapl_type(arch->valuestring);
    if (sensor && sensor->valuestring) p->sensor = get_rapl_config(sensor->valuestring);
    snprintf(p->vendor, sizeof(p->vendor), "%s",
             (vendor && vendor->valuestring) ? vendor->valuestring : "Intel");

    p->freq             = cJSON_GetObjectItem(params, "freq")->valuedouble;
    p->total_operations = cJSON_GetObjectItem(params, "n_work")->valueint;
    p->n_stat           = cJSON_GetObjectItem(params, "n_stat")->valueint;
    cJSON *nc = cJSON_GetObjectItem(params, "n_cores");
    p->n_cores = nc ? nc->valueint : 8;
    cJSON *sf = cJSON_GetObjectItem(params, "seq_fraction");
    p->seq_fraction = sf ? (float)sf->valuedouble : 0.0f;

    cJSON_Delete(json);
    return 0;
}

int create_output_files(const char *base_path, const params_t *p,
                        const int *n_cores_array, int n_cores_count,
                        const float *seq_fraction_array, int seq_fraction_count)
{
    cJSON *root   = cJSON_CreateObject();
    cJSON *params = cJSON_CreateObject();

    time_t now = time(NULL); struct tm tm_now; localtime_r(&now, &tm_now);
    char date_str[32];
    strftime(date_str, sizeof(date_str), "%Y-%m-%d %H:%M:%S", &tm_now);

    cJSON_AddStringToObject(params, "date",   date_str);
    cJSON_AddStringToObject(params, "vendor", p->vendor);
    cJSON_AddNumberToObject(params, "arch",   p->arch);
    cJSON_AddNumberToObject(params, "sensor", p->sensor);
    cJSON_AddNumberToObject(params, "freq",   p->freq);
    cJSON_AddNumberToObject(params, "n_work", p->total_operations);
    cJSON_AddNumberToObject(params, "n_stat", p->n_stat);

    if (n_cores_array && n_cores_count > 0) {
        if (n_cores_count > 1) {
            cJSON *arr = cJSON_CreateIntArray(n_cores_array, n_cores_count);
            cJSON_AddItemToObject(params, "n_cores", arr);
        } else {
            cJSON_AddNumberToObject(params, "n_cores", n_cores_array[0]);
        }
    } else {
        cJSON_AddNumberToObject(params, "n_cores", p->n_cores);
    }

    if (seq_fraction_array && seq_fraction_count > 0) {
        if (seq_fraction_count > 1) {
            cJSON *arr = cJSON_CreateFloatArray(seq_fraction_array, seq_fraction_count);
            cJSON_AddItemToObject(params, "seq_fraction", arr);
        } else {
            cJSON_AddNumberToObject(params, "seq_fraction", seq_fraction_array[0]);
        }
    } else {
        cJSON_AddNumberToObject(params, "seq_fraction", p->seq_fraction);
    }

    cJSON_AddItemToObject(root, "params",      params);
    cJSON_AddItemToObject(root, "energy",      cJSON_CreateObject());
    cJSON_AddItemToObject(root, "time",        cJSON_CreateObject());
    cJSON_AddItemToObject(root, "temperature", cJSON_CreateObject());
    cJSON_AddItemToObject(root, "voltage",     cJSON_CreateObject());

    char json_path[512];
    snprintf(json_path, sizeof(json_path), "%s.json", base_path);
    char *out = cJSON_Print(root);
    FILE *f = fopen(json_path, "w");
    if (!f) { free(out); cJSON_Delete(root); return -1; }
    fputs(out, f); fclose(f); free(out);
    cJSON_Delete(root);

    char csv_path[512];
    snprintf(csv_path, sizeof(csv_path), "%s.csv", base_path);
    FILE *csv = fopen(csv_path, "w");
    if (csv) {
        fprintf(csv, "Energy_J,Time_s,Temperature_C,Voltage_V,N_cores,Seq_frac,Nbarriers\n");
        fclose(csv);
    }

    return 0;
}

void update_subjson_double_array(const char *filename, const char *subkey,
                                 const char *array_key, const double *values, int count)
{
    FILE *f = fopen(filename, "r");
    if (!f) { perror("fopen"); return; }
    fseek(f, 0, SEEK_END); long len = ftell(f); rewind(f);
    char *data = malloc(len + 1);
    fread(data, 1, len, f); data[len] = '\0'; fclose(f);

    cJSON *root = cJSON_Parse(data); free(data);
    if (!root) { fprintf(stderr, "JSON parse error in %s\n", filename); return; }

    cJSON *sub = cJSON_GetObjectItem(root, subkey);
    if (!sub) {
        sub = cJSON_CreateObject();
        cJSON_AddItemToObject(root, subkey, sub);
    }
    cJSON *arr = cJSON_CreateArray();
    for (int i = 0; i < count; i++)
        cJSON_AddItemToArray(arr, cJSON_CreateNumber(values[i]));

    cJSON *existing = cJSON_GetObjectItem(sub, array_key);
    if (existing) cJSON_ReplaceItemInObject(sub, array_key, arr);
    else          cJSON_AddItemToObject(sub, array_key, arr);

    char *out = cJSON_Print(root);
    f = fopen(filename, "w");
    if (f) { fputs(out, f); fclose(f); } else perror("fopen write");
    free(out); cJSON_Delete(root);
}

char *build_name(const parallel_sim_params_t *sim)
{
    if (!sim) return NULL;
    size_t len = snprintf(NULL, 0, "%d_%.2f_%d_%llu",
                          sim->nthreads, sim->seq_fraction, sim->nbarriers,
                          (unsigned long long)sim->total_units_per_barrier) + 1;
    char *name = malloc(len);
    if (!name) { perror("malloc"); return NULL; }
    snprintf(name, len, "%d_%.2f_%d_%llu",
             sim->nthreads, sim->seq_fraction, sim->nbarriers,
             (unsigned long long)sim->total_units_per_barrier);
    return name;
}

/* ── CSV ─────────────────────────────────────────────────────────────────── */

void append_csv_row(const char *base_path, double energy, double time,
                    double temp, double voltage,
                    int n_cores, double seq_frac, int nbarriers)
{
    char csv_path[512];
    snprintf(csv_path, sizeof(csv_path), "%s.csv", base_path);
    FILE *csv = fopen(csv_path, "a");
    if (!csv) return;
    fprintf(csv, "%.6f,%.6f,%.2f,%.3f,%d,%.2f,%d\n",
            energy, time, temp, voltage, n_cores, seq_frac, nbarriers);
    fclose(csv);
}
