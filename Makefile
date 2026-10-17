# MicrasPCB: one entry point for people, agents and CI. `make help` lists the targets.
include versions.env

PCB := pcb +$(PCB_TOOLCHAIN)
TOOL := uv run micras-pcb
BOARDS := $(notdir $(patsubst %/pcb.toml,%,$(wildcard boards/*/pcb.toml)))
# Boards replicated from a previous revision (boards/<board>/previous/board.json + changes.toml).
PREVIOUS_BOARDS := main encoder bluetooth

.PHONY: help setup gen check build warnings test layout-check sch erc lvs previous drc dfm pytest lint parts parts-online outputs fab review all clean

# The gates `make check` runs, in order. Each runs even when an earlier one fails.
GATES := build warnings test layout-check sch erc lvs previous drc dfm pytest lint parts

help: ## list targets
	@grep -hE '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-13s %s\n", $$1, $$2}'

setup: ## install the Python tools and the pinned Zener toolchain
	uv sync
	pcb toolchain install $(PCB_TOOLCHAIN)

gen: ## regenerate every generated file from the sources (Zener, spec, rules)
	$(PCB) sync
	$(PCB) fmt .
	@# The schematic, root and module sheets, is written afresh each time, then placed from
	@# boards/<board>/schematic/*.toml, parts without an entry drafted: `pcb apply` on an existing
	@# schematic only repairs netlist differences, leaving the power symbols, labels and wires a
	@# pin has left (ERC reports them dangling) and drawing new connections in its own style.
	@# Generation is deterministic.
	@for b in $(BOARDS); do rm -f boards/$$b/layout/*.kicad_sch; $(PCB) apply --no-open boards/$$b/$$b.zen || exit 1; done
	$(TOOL) sch
	$(TOOL) rules
	$(TOOL) mech

build: ## evaluate the Zener sources
	$(PCB) fmt --check .
	$(PCB) sync --check
	@status=0; for b in $(BOARDS); do $(PCB) build boards/$$b/$$b.zen || status=1; done; exit $$status

warnings: ## no build warnings (voltage ranges outside a part's operating range, capacitor ratings)
	@status=0; for b in $(BOARDS); do $(PCB) build -D warnings boards/$$b/$$b.zen || status=1; done; exit $$status

test: ## Zener test benches (components, then each board's test/ benches)
	@status=0; $(PCB) test components || status=1; for b in $(BOARDS); do $(PCB) test boards/$$b || status=1; done; exit $$status

layout-check: ## layouts in sync with the netlist and the spec
	@status=0; for b in $(BOARDS); do $(PCB) layout --check boards/$$b/$$b.zen || status=1; done; \
	$(TOOL) rules --check || status=1; $(TOOL) mech --check || status=1; exit $$status

sch: ## placed sheets clean and current; entries name what their sheets have; drafted parts counted
	$(TOOL) sch --check

erc: ## KiCad ERC on the generated schematics
	$(TOOL) erc

lvs: ## generated schematic vs PCB connectivity
	$(TOOL) lvs

previous: ## connectivity of each replicated board vs its previous revision + boards/<board>/changes.toml
	@status=0; for b in $(PREVIOUS_BOARDS); do $(TOOL) previous compare $$b || status=1; done; exit $$status

drc: ## KiCad DRC with the JLCPCB rules
	$(TOOL) drc

dfm: ## Diode DFM against the JLCPCB PDK
	$(TOOL) dfm

pytest: ## Python design tests
	uv run pytest -q

lint: ## Python lint and format
	@status=0; uv run ruff check tools tests || status=1; uv run ruff format --check tools tests || status=1; exit $$status

parts: ## every part mapped to an LCSC number
	$(TOOL) parts

parts-online: ## JLCPCB stock and basic/extended status for every part (run before ordering)
	$(TOOL) parts --online

check: ## every gate CI runs: all of them, then a summary; fails if any gate failed
	@failed=""; for g in $(GATES); do \
		echo "=== gate $$g"; $(MAKE) --no-print-directory $$g || failed="$$failed $$g"; \
	done; \
	echo "=== gates"; \
	for g in $(GATES); do case " $$failed " in *" $$g "*) echo "  FAIL  $$g";; *) echo "  pass  $$g";; esac; done; \
	test -z "$$failed"

outputs: ## review outputs (schematic, layers, renders, 3D)
	$(TOOL) outputs

fab: ## JLCPCB fab package
	$(TOOL) fab

review: outputs fab ## review outputs and fab package (what CI uploads)

all: gen check review ## regenerate, check and build everything

clean:
	rm -rf build
