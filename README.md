## Project Description: Batch Download of CIFs from ICSD, Materials Project, and OQMD Databases

This repository is used to batch download CIF files from multiple materials databases. It currently supports:

- **ICSD**: Download CIF files through the ICSD API Services;
- **Materials Project (MP)**: Batch download CIF files using mp-api with specified conditions;
- **OQMD**: Retrieve structures via the OQMD REST API and write them out as CIF files.

It is recommended to configure the environment in the root directory of this repository and use **Python 3.11+**.

---

## Environment Setup

```bash
pip install -r requirements.txt
```

---

## Directory Structure and Features

- `ICSD/`
  - `ICSDClient.py`: Client wrapping the ICSD Web Service.
    - Supports login, search, and batch download of CIFs.
    - Example included: **Download all crystalline CIFs containing S / Se / Te**.
  - `requirements.txt`: ICSD client dependencies (integrated into root `requirements.txt`).

- `MP/`
  - `download_mp_cifs.py`: Batch download CIFs from **Materials Project**.
    - Uses official `mp-api` (new MP API client).
    - Supports:
      - Download by `material_id` list: `--ids / --ids-file`;
      - Query by elements / formula / chemical system: `--elements / --formula / --chemsys`;
      - Filter by **energy above hull**: `--eabove-hull`.
    - Default behavior (no query arguments):
      - **Material contains at least one of S / Se / Te**;
      - And **energy above hull > 0.5 eV/atom**;
      - Results written to the specified directory; existing files can be skipped.
  - `requirements.txt`: MP-specific dependencies (now managed by root `requirements.txt`).

- `OQMD/`
  - `download_oqmd_cifs.py`: Batch download CIFs from **OQMD**.
    - Calls OQMD REST API (`http://oqmd.org/oqmdapi/formationenergy`) for `unit_cell` and `sites`;
    - Builds structures with `pymatgen` and writes CIFs.
    - Supports:
      - Download by `entry_id` list: `--ids / --ids-file`;
      - Filter by element set / composition / stability: `--element-set / --composition / --stability / --filter`.
    - Default behavior (no query arguments):
      - **Contains at least one of S / Se / Te** (`element_set=(S-Se-Te)`);
      - And **stability > 0.5 eV/atom** (i.e., 0.5 eV/atom above the convex hull).
  - `requirements.txt`: OQMD-specific dependencies (integrated into root `requirements.txt`).

- `requirements.txt` (root)
  - Consolidates dependencies for **ICSD + MP + OQMD**:
    - `requests`, `beautifulsoup4`, `lxml`, `pandas`, `numpy`, `mp-api`, etc.

---

## Common Usage Examples

> Commands below assume you are in the repository root with the virtual environment activated:  
> `cd d:\Databases_CIFs_download\DataBases_Cif_download` and `.\.venv\Scripts\Activate.ps1`

### 1. Download CIFs from Materials Project

- Default: material contains at least one of S / Se / Te and energy above hull > 0.5:

```powershell
python MP\download_mp_cifs.py -o .\mp_cifs
```

- Custom energy above hull lower bound, e.g. > 0.8 eV/atom:

```powershell
python MP\download_mp_cifs.py --eabove-hull 0.8 -o .\mp_cifs
```

- Download by specified `material_id` list:

```powershell
python MP\download_mp_cifs.py --ids mp-149 mp-1234 -o .\mp_cifs
```

### 2. Download CIFs from OQMD

- Default: at least one of S / Se / Te and stability > 0.5 eV/atom:

```powershell
python OQMD\download_oqmd_cifs.py -o .\oqmd_cifs
```

- Download by entry_id list:

```powershell
python OQMD\download_oqmd_cifs.py --ids 1216058 16974 -o .\oqmd_cifs
```

### 3. Using the ICSD Client

Run the example `main()` in the `ICSD` directory or call methods in `ICSDClient` as needed, e.g.:

```powershell
cd ICSD
python ICSDClient.py
```

Fill in your own ICSD account and password in the script, and adjust filter conditions and output directory as needed.
