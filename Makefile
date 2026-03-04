CC = gcc
CFLAGS = -Wall -Wextra -g -pthread
SRC = main.c parallel_sim.c json_utils.c
OUT = counter

all: $(OUT)

$(OUT): $(SRC)
	$(CC) $(CFLAGS) -o $@ $^ -lm -lcjson

clean:
	rm -f $(OUT)