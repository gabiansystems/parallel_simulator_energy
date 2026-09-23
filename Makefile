CC     = gcc
CFLAGS = -O2 -Wall -Wextra -g \
         -Ibenchmarks -Ienergy_tool -Iutils
LDFLAGS = -pthread -lm

SRC = main.c \
      energy_tool/counter.c \
      benchmarks/parallel_sim.c \
      utils/json_utils.c \
      utils/cJSON.c

OUT = counter

all: $(OUT)

$(OUT): $(SRC)
	$(CC) $(CFLAGS) -o $@ $^ $(LDFLAGS)

test:
	$(MAKE) -C tests

clean:
	rm -f $(OUT)
	$(MAKE) -C tests clean
