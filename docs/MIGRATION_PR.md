Migration PR template
=====================

This file contains a suggested migration PR description and the key changes
to make `mail_summariser` consume `modelito` as an external dependency.

Suggested PR summary
--------------------
Move in-repo `modelito` usage to the external `modelito` package.

Files to change
---------------
- Update CI/test scripts to add `PYTHONPATH` pointing to the external package during validation.
- Replace any internal-only helper functions if the package API differs; add small adapter shims if needed.
- Remove or archive the in-repo `modelito/` directory after validation.

Example CI snippet (GitHub Actions) to run tests with an installed package from a wheel:

```yaml
# Install modelito from a wheel or TestPyPI before running tests
- name: Install modelito
  run: |
    python -m pip install --upgrade pip
    pip install modelito==0.1.0 --extra-index-url https://test.pypi.org/simple || true
```

Local validation (without publishing):

```bash
# from repository root
./scripts/run_with_local_modelito.sh
```

Notes
-----
- Keep compatibility shims in this repo for short-term use if the external
  package changes its API; prefer stabilizing the external API instead.
