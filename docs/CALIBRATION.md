Calibration CLI
===============

Use `scripts/calibrate_timeout_catalog.py` to measure model latency in your
environment and generate a JSON report. This helps produce environment-specific
timeouts for the `modelito` timeout catalog.

Basic usage:

```sh
python scripts/calibrate_timeout_catalog.py --models llama-2-13b,vicuna-13b --out calibrated.json
```

Notes:

- The tool requires a running Ollama server at `http://localhost:11434` by default.
- The report contains measured `avg_seconds_per_1000_input_tokens` for each model.
- Run the script on the machine where Ollama serves to capture representative timings.

CI:

- Calibration is environment-specific and not suitable for default CI runs.
- If you want to run it in CI, add a dedicated self-hosted runner with Ollama installed
  and enable the `RUN_CALIBRATE_TEST=1` environment variable.
