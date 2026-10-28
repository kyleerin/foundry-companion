# Runtime dependency audit — 2026-10-28

Tool: `pip-audit 2.9.0`, PyPI advisory service, scanning a frozen list from the
project's Python 3.9.6 environment. The auditing tools were installed separately
in scratch space, not in the app environment. No `--fix` was run.

Result: **23 known advisories in 2 packages**, exit status 1. The scan completed
despite a LibreSSL compatibility warning from the audit tool's urllib3.
`pip check` passed separately; dependency compatibility does not imply security.

## Reported advisories

| Package | Installed | IDs | Reported fix |
| --- | --- | --- | --- |
| aiohttp | 3.13.5 | PYSEC-2026-2104, PYSEC-2026-2105, PYSEC-2026-2106 | 3.14.0 |
| aiohttp | 3.13.5 | PYSEC-2026-237, PYSEC-2026-2107, PYSEC-2026-2108, PYSEC-2026-2109, PYSEC-2026-2110, PYSEC-2026-2111, PYSEC-2026-2112, PYSEC-2026-2113 | 3.14.1 |
| aiohttp | 3.13.5 | PYSEC-2026-3546, PYSEC-2026-3547 | 3.14.2 |
| aiohttp | 3.13.5 | PYSEC-2026-3545 | 3.14.3 |
| aiohttp | 3.13.5 | GHSA-5wr8-gcqf-gqf3, GHSA-2g87-pp6c-29x5, GHSA-494j-54xm-rwp3, GHSA-pqxq-w44r-73xw, GHSA-9xw5-w5jj-pvcg, GHSA-gx76-c99x-2c96, GHSA-6cjc-53gc-5rqm, GHSA-f9xw-jh8m-3mwq | 3.14.4 |
| multidict | 6.7.1 | PYSEC-2026-4244 | 6.9.1 |

These are scanner-reported package matches, not 23 independently demonstrated
application exploits. Advisories can change; rerun after dependency updates.

PyPI metadata for [aiohttp 3.14.4](https://pypi.org/project/aiohttp/3.14.4/) and
[multidict 6.9.1](https://pypi.org/project/multidict/6.9.1/) declares Python >=3.10.
The project's Python 3.9 floor prevents simply applying these fixes. Raising the
floor and refreshing the lock/install matrix is a release decision.

## Reproduce

In the app environment, write a fully pinned runtime list into gitignored `dist/`:

```sh
.venv/bin/python -m pip freeze > dist/runtime-requirements.txt
```

Install `pip-audit` in a separate tools environment, then use that environment's
command:

```sh
pip-audit -r dist/runtime-requirements.txt --no-deps --disable-pip
```

`--no-deps` is appropriate here only because the frozen file includes all resolved
runtime dependencies. Do not apply it to the top-level `requirements.txt` alone.
The audit queries public package/advisory services; no source or vault files are
uploaded. This scan excludes Python tooling, browser/CDN packages, Foundry,
dnd5e, and the operating system. It is not a complete security certification.
