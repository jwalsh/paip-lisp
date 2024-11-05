.PHONY: help install clean validate-chunks chunks chunks-i chunks-n chunks-other chunks-gpt4 chunks-safe chunks-aggressive chunks-custom little-lisper little-lisper-custom

help: ## Show this help message
	@echo 'Usage: make [target]'
	@echo ''
	@echo 'Targets:'
	@awk 'BEGIN {FS = ":.*##"; printf "\n"} /^[a-zA-Z_-]+:.*?##/ { printf "  %-24s %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

install: ## Install required dependencies using poetry
	poetry install

# Basic chunking operations
chunks: ## Process PAIP.txt with defaults (50% safety factor)
	poetry run python chunk_processor.py

chunks-i: ## Process PAIP.txt in interactive mode
	poetry run python chunk_processor.py -i

chunks-n: ## Process PAIP.txt with 5 chunks
	poetry run python chunk_processor.py -n 5

chunks-other: ## Process another file (usage: make chunks-other FILE=myfile.txt)
	poetry run python chunk_processor.py $(FILE)

# Model-specific targets
chunks-gpt4: ## Process using GPT-4 context window
	poetry run python chunk_processor.py -m gpt-4

# Safety factor variants
chunks-safe: ## Process with conservative token limits (30% of max)
	poetry run python chunk_processor.py -s 0.3

chunks-aggressive: ## Process with aggressive token limits (80% of max)
	poetry run python chunk_processor.py -s 0.8

chunks-custom: ## Process with custom safety factor (usage: make chunks-custom SAFETY=0.4)
	poetry run python chunk_processor.py -s $(SAFETY)

# Little Lisper conversion
little-lisper: chunks ## Convert PAIP.txt to Little Schemer style org-mode
	poetry run python chunk_processor.py --little-lisper

little-lisper-custom: ## Convert custom file to Little Schemer style (usage: make little-lisper-custom FILE=myfile.txt)
	poetry run python chunk_processor.py $(FILE) --little-lisper

# Validation and cleanup
validate-chunks: ## Validate line counts in chunks match original file
	@echo "Original file:"
	@wc -l PAIP.txt
	@echo "\nChunked files:"
	@wc -l chunks/chunk_*
	@echo "\nChecking for differences..."
	@diff <(wc -l PAIP.txt) <(cat chunks/chunk_* | wc -l) || echo "Warning: Line counts differ!"

clean: ## Remove chunks directory and cached files
	rm -rf chunks/
	rm -rf __pycache__/
	rm -rf .pytest_cache/
	rm -f little-lisper-paip.org

# Combination targets
process-all: clean chunks validate-chunks ## Clean, chunk, and validate in one step

convert-all: process-all little-lisper ## Process file and convert to Little Lisper style

# Development helpers
check-ollama: ## Check if Ollama is running and llama2 model is available
	@curl -s http://localhost:11434/api/tags > /dev/null && echo "Ollama is running" || echo "Ollama is not running"
	@curl -s http://localhost:11434/api/tags | grep -q "llama3.2" && echo "llama3.2 model is available" || echo "llama3.2 model is not available"

setup-dev: install ## Setup development environment
	poetry install
	@echo "Checking Ollama installation..."
	@make check-ollama

# Default target
.DEFAULT_GOAL := help
