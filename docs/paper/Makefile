# Build the manuscript. `make` produces main.pdf with references resolved.
#
#   make          full build (latex, bibtex, latex, latex)
#   make quick    one pass, for checking a prose edit
#   make check    report errors, undefined references and overfull boxes
#   make figures  compile each figure alone, to isolate a TikZ error
#   make clean    remove build artifacts, keep main.pdf and main.bbl

TEX    := pdflatex -interaction=nonstopmode -file-line-error
SRC    := main.tex appendix.tex references.bib \
          $(filter-out figures/_probe-preamble.tex,$(wildcard figures/*.tex))

.PHONY: all quick check figures clean distclean

all: main.pdf

main.pdf: $(SRC)
	@$(TEX) main.tex > /dev/null
	@bibtex main > /dev/null || true
	@$(TEX) main.tex > /dev/null
	@$(TEX) main.tex > /dev/null
	@$(MAKE) --no-print-directory check

quick:
	@$(TEX) main.tex > /dev/null
	@$(MAKE) --no-print-directory check

# Anything printed here should be empty before the draft is circulated.
check:
	@echo "pages: $$(pdfinfo main.pdf 2>/dev/null | awk '/Pages/{print $$2}')"
	@grep -E '^\./|^!' main.log | head -20 || true
	@grep -c 'undefined' main.log | awk '{if ($$1>0) print "undefined references: " $$1}'
	@awk '/Overfull \\hbox \([0-9]{3,}/{n++} END{if (n) print "overfull boxes >100pt: " n}' main.log

# Each figure compiled standalone, so a TikZ error names its own file
# rather than surfacing as a line number in main.tex.
figures:
	@for f in $(filter-out figures/_probe-preamble.tex,$(wildcard figures/*.tex)); do \
	  printf '%-36s' "$$f"; \
	  cat figures/_probe-preamble.tex "$$f" > fig-probe.tex; \
	  printf '\\end{document}\n' >> fig-probe.tex; \
	  if $(TEX) fig-probe.tex > /dev/null 2>&1; then echo "ok"; \
	  else echo "FAILED"; grep -m3 '^\./\fig-probe\|^!' fig-probe.log; fi; \
	done; rm -f fig-probe.*

clean:
	@rm -f main.aux main.log main.out main.blg fig-probe.*

distclean: clean
	@rm -f main.pdf main.bbl
