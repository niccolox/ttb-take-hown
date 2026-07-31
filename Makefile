VENV=.venv/bin
serve:
	$(VENV)/python -m uvicorn api.main:app --port 8123
test:
	$(VENV)/python -m pytest api/tests/ -q
eval:
	$(VENV)/python api/eval/spike.py
golden:
	$(VENV)/python api/eval/generate_golden.py
smoke:
	@bash scripts/smoke.sh
