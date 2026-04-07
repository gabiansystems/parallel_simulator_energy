CC = gcc
CFLAGS = -Wall -Wextra -g
LDFLAGS = -pthread

MAIN ?= main_off.c
TARGET ?= counter_off

SRC = $(MAIN) parallel_sim.c json_utils.c

all: $(TARGET)

$(TARGET): $(SRC)
	$(CC) $(CFLAGS) -o $@ $^ $(LDFLAGS) -lm -lcjson

on:
	$(MAKE) MAIN=main_on.c TARGET=counter_on CFLAGS+=" -DTEST_MODE"

clean:
	rm -f counter_off counter_on