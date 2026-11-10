.PHONY: help install sample demo serve test smoke clean

help:
	@echo "Hookforge"
	@echo "  make install   install python deps"
	@echo "  make sample    build the synthetic demo clip + transcript"
	@echo "  make demo      run the full agent chain on the sample clip"
	@echo "  make serve     start the dashboard on http://127.0.0.1:8000"
	@echo "  make test      run the pipeline test suite"
	@echo "  make smoke     run the API checks"
	@echo "  make clean     remove generated data (keeps samples/)"

install:
	pip install -r requirements.txt

sample:
	python scripts/make_sample_assets.py

demo:
	python scripts/demo_run.py

serve:
	uvicorn app.main:app --reload --port 8000

test:
	python tests/test_pipeline.py

smoke:
	python scripts/smoke_api.py

clean:
	rm -rf data
	find . -name "__pycache__" -type d -prune -exec rm -rf {} +
