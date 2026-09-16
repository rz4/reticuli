# The producer. `rebuild` runs this in a clean workspace holding only the
# claim's pinned inputs; the default target must produce the generated output.
CC ?= cc
CFLAGS ?= -O2 -Wall

wordcount: wordcount.c
	$(CC) $(CFLAGS) -o $@ $<

.PHONY: clean
clean:
	rm -f wordcount
