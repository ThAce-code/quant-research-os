# Environment and local research artifacts

The validated workstation uses Windows PowerShell and Python 3.12 in the Conda
environment `quant`. Launchers expect `%USERPROFILE%/miniconda3/envs/quant/python.exe`.

Qlib is an external checkout, not project-owned source. Its locked revision is:

- Repository: https://github.com/microsoft/qlib.git
- Commit: `79633dd9506ea689e5400dea0197717b5b3d74b7`
- Local directory: `vendor/qlib` (ignored by this repository)

To obtain the corresponding source in a fresh checkout:

```powershell
git clone https://github.com/microsoft/qlib.git vendor/qlib
git -C vendor/qlib checkout 79633dd9506ea689e5400dea0197717b5b3d74b7
```

Observed package versions on the validated workstation (an inventory, not a
guarantee that these development builds are available from a public package index):

| Package | Version |
|---|---|
| baostock | 0.9.3 |
| pyqlib | 0.9.8.dev32 |
| numpy | 2.5.2 |
| pandas | 2.3.3 |
| scipy | 1.18.1 |
| lightgbm | 4.7.0 |
| pyarrow | 25.0.1 |
| filelock | 3.32.5 |
| matplotlib | 3.11.1 |
| pytest | 9.1.1 |

Git stores project source, configurations, tests, documentation and the frozen M0
source/manifest. Market datasets, experiment outputs, SQLite databases, caches
and the vendor checkout remain local and are not uploaded. README experiment
links therefore refer to artifacts in the original workspace, not hosted files.

A new clone alone cannot reproduce the exact frozen run: the baseline manifest
references the original artifact location and hashes. Restoring that snapshot is
required for its strict M1/M2 identity checks; downloading a fresh vendor snapshot
does not establish identity with the old one. Keep the existing local data intact.

Git preserves file bytes without automatic newline conversion because the
research manifests contain source SHA256 hashes.
