CC     = gcc
CFLAGS = -Wall -Wextra -g \
         -I../benchmarks -I../utils -I../energy_tool \
         -DUNITY_INCLUDE_DOUBLE
UNITY  = unity/unity.c
LIBS   = -lm

.PHONY: all clean

all: test_sim
	@echo ""
	@./test_sim

# test_sim: pure C logic tests, no root needed
test_sim: test_sim.c ../benchmarks/parallel_sim.c $(UNITY)
	$(CC) $(CFLAGS) -o $@ $^ $(LIBS) -pthread

# test_probes: hardware probes, requires root (sudo-g5k on G5K)
test_probes: test_probes.c $(UNITY)
	$(CC) $(CFLAGS) -o $@ $^ $(LIBS)
	@echo "Run with: sudo-g5k ./test_probes"

clean:
	rm -f test_sim test_probes
