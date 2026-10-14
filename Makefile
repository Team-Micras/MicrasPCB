# MicrasPCB: one entry point for people, agents and CI. `make help` lists the targets.
include versions.env

PCB := pcb +$(PCB_TOOLCHAIN)
TOOL := uv run micras-pcb
BOARDS := $(notdir $(patsubst %/pcb.toml,%,$(wildcard boards/*/pcb.toml)))

.PHONY: help setup gen check build test layout-check erc lvs previous drc dfm pytest lint parts parts-online outputs fab review all clean

help: ## list targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-13s %s\n", $$1, $$2}'

setup: ## install the Python tools and the pinned Zener toolchain
	uv sync
	pcb toolchain install $(PCB_TOOLCHAIN)

gen: ## regenerate every generated file from the sources (Zener, spec, rules)
	$(PCB) sync
	$(PCB) fmt .
	@for b in $(BOARDS); do $(PCB) apply --no-open boards/$$b/$$b.zen || exit 1; done
	$(TOOL) rules
	$(TOOL) mech

build: ## evaluate the Zener sources
	$(PCB) fmt --check .
	$(PCB) sync --check
	@for b in $(BOARDS); do $(PCB) build boards/$$b/$$b.zen || exit 1; done

test: ## Zener test benches
	$(PCB) test components
	$(PCB) test boards

layout-check: ## layouts in sync with the netlist and the spec
	@for b in $(BOARDS); do $(PCB) layout --check boards/$$b/$$b.zen || exit 1; done
	$(TOOL) rules --check
	$(TOOL) mech --check

erc: ## KiCad ERC on the generated schematics
	$(TOOL) erc

lvs: ## generated schematic vs PCB connectivity
	$(TOOL) lvs

previous: ## main board connectivity vs the previous revision + boards/main/changes.toml
	$(TOOL) previous compare main

drc: ## KiCad DRC with the JLCPCB rules
	$(TOOL) drc

dfm: ## Diode DFM against the JLCPCB PDK
	$(TOOL) dfm

pytest: ## Python design tests
	uv run pytest -q

lint: ## Python lint and format
	uv run ruff check tools tests
	uv run ruff format --check tools tests

parts: ## every part mapped to an LCSC number
	$(TOOL) parts

parts-online: ## JLCPCB stock and basic/extended status for every part (run before ordering)
	$(TOOL) parts --online

check: build test layout-check erc lvs previous drc dfm pytest lint parts ## every gate CI runs

outputs: ## review outputs (schematic, layers, renders, 3D)
	$(TOOL) outputs

fab: ## JLCPCB fab package
	$(TOOL) fab

review: outputs fab ## review outputs and fab package (what CI uploads)

all: gen check review ## regenerate, check and build everything

clean:
	rm -rf build
