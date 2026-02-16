## Project Description: Batch Download of CIFs from ICSD, Materials Project, and OQMD Databases

This repository is used to batch download CIF files from multiple materials databases. It currently supports:

- **ICSD**: Download CIF files through the ICSD API Services;
- **Materials Project (MP)**: Batch download CIF files using mp-api with specified conditions;
- **OQMD**: Retrieve structures via the OQMD REST API and write them out as CIF files.

It is recommended to configure the environment in the root directory of this repository and use **Python 3.11+**.

---

## Environment Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```
---

### 1. Download CIFs from Materials Project

- Default: material contains at least one of S / Se / Te and energy above hull > 0.5:

```powershell
cd Material_Project
python3 download_mp_cifs.py
```

### 2. Download CIFs from OQMD

- Default: at least one of S / Se / Te and stability > 0.5 eV/atom:

```powershell
cd OQMD
python3 download_oqmd_cifs.py
```

### 3. Using the ICSD Client

Run the example `main()` in the `ICSD` directory or call methods in `ICSDClient` as needed, e.g.:

```powershell
cd ICSD
python3 ICSDClient.py
```

Fill in your own ICSD account and password in the script, and adjust filter conditions and output directory as needed.
