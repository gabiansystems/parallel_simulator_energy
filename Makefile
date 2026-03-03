CC = gcc
CFLAGS = -Wall -Wextra -g -pthread
SRC = main.c parallel_sim.c json_utils.c cJSON.c
OUT = counter

all: $(OUT)

$(OUT): $(SRC)
	$(CC) $(CFLAGS) -o $@ $^ -lm

clean:
	rm -f $(OUT)