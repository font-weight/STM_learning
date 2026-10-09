CC ?= cc
PYTHON ?= python3
CFLAGS ?= -std=c11 -O0 -g -Wall -Wextra -Werror -Wpedantic
IMPL ?= student.c
BUILD_DIR ?= build

.PHONY: all build check exercise-check release-check test-list sanitize clean
all: build
build: $(BUILD_DIR)/test_stream

$(BUILD_DIR)/test_stream: $(IMPL) test_stream.c stream.h
	mkdir -p $(BUILD_DIR)
	$(CC) $(CFLAGS) -I. $(IMPL) test_stream.c -o $@

check: $(BUILD_DIR)/test_stream
	./$(BUILD_DIR)/test_stream

exercise-check: check

release-check: $(BUILD_DIR)/test_stream
	$(MAKE) IMPL=reference/stream_reference.c BUILD_DIR=build-reference build
	$(PYTHON) verify_release.py --student $(BUILD_DIR)/test_stream --oracle build-reference/test_stream

test-list: $(BUILD_DIR)/test_stream
	./$(BUILD_DIR)/test_stream --list

sanitize:
	$(MAKE) BUILD_DIR=build-sanitize CFLAGS="$(CFLAGS) -fsanitize=address,undefined -fno-omit-frame-pointer" check

clean:
	rm -rf build build-sanitize build-reference build-reference-sanitize
