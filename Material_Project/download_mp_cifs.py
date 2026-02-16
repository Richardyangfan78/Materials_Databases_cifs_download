# -*- coding: utf-8 -*-
"""
Batch download CIF files from Materials Project.
Uses mp-api: https://pypi.org/project/mp-api/
API Key can be obtained from https://www.materialsproject.org/dashboard.
It is recommended to set the API Key via the MP_API_KEY environment variable.
"""

import os
import argparse
from pathlib import Path

# Default API Key (can also be set via environment variable MP_API_KEY)
DEFAULT_API_KEY = os.environ.get("MP_API_KEY", "8i00vBC1hXg3nVo0t0QvPbSd1GVbz9si")


def download_cifs_by_material_ids(
    material_ids,
    cif_dir="./cifs",
    api_key=DEFAULT_API_KEY,
    skip_existing=True,
):
    """
    Batch download CIFs by material_id list from Materials Project.

    Parameters
    ----------
    material_ids : list[str]
        e.g. ["mp-149", "mp-1234"]
    cif_dir : str
        Directory to save CIF files
    api_key : str
        Materials Project API Key
    skip_existing : bool
        Whether to skip if the target CIF already exists

    Returns
    -------
    tuple (success_count, fail_list)
    """
    from mp_api.client import MPRester

    Path(cif_dir).mkdir(parents=True, exist_ok=True)
    success = 0
    failed = []

    with MPRester(api_key) as mpr:
        for mid in material_ids:
            mid = str(mid).strip()
            if not mid or not mid.startswith("mp-"):
                continue
            out_path = os.path.join(cif_dir, f"{mid}.cif")
            if skip_existing and os.path.isfile(out_path):
                success += 1
                continue
            try:
                structure = mpr.get_structure_by_material_id(mid)
                if structure is not None:
                    structure.to(fmt="cif", filename=out_path)
                    success += 1
                else:
                    failed.append((mid, "no structure"))
            except Exception as e:
                failed.append((mid, str(e)))

    return success, failed


def download_cifs_by_query(
    elements=None,
    formula=None,
    chemsys=None,
    energy_above_hull=None,
    max_results=1000,
    cif_dir="./cifs",
    api_key=DEFAULT_API_KEY,
    skip_existing=True,
):
    """
    Query Materials Project by elements/formula/chemical system and download matching CIFs.

    Parameters
    ----------
    elements : list[str], optional
        Materials containing at least these elements, e.g. ["Si", "O"]
    formula : str, optional
        Formula, e.g. "SiO2" or "ABC3"
    chemsys : str, optional
        Chemical system, e.g. "Si-O"
    energy_above_hull : tuple[float, float], optional
        energy above hull range (min, max) in eV/atom, e.g. (0.5, None) for > 0.5
    max_results : int
        Maximum number of entries to download (within API pagination limits)
    cif_dir : str
        Directory to save CIFs
    api_key : str
        API Key
    skip_existing : bool
        Whether to skip existing CIFs

    Returns
    -------
    tuple (success_count, fail_list)
    """
    from mp_api.client import MPRester

    Path(cif_dir).mkdir(parents=True, exist_ok=True)
    success = 0
    failed = []

    chunk_size = min(1000, max_results)
    num_chunks = max(1, (max_results + chunk_size - 1) // chunk_size)

    search_kw = dict(
        elements=elements,
        formula=formula,
        chemsys=chemsys,
        fields=["material_id", "structure"],
        chunk_size=chunk_size,
        num_chunks=num_chunks,
    )
    if energy_above_hull is not None:
        search_kw["energy_above_hull"] = energy_above_hull

    with MPRester(api_key) as mpr:
        docs = list(mpr.materials.summary.search(**search_kw))
        for doc in docs:
            mid = str(doc.material_id)
            out_path = os.path.join(cif_dir, f"{mid}.cif")
            if skip_existing and os.path.isfile(out_path):
                success += 1
                continue
            try:
                if getattr(doc, "structure", None) is not None:
                    doc.structure.to(fmt="cif", filename=out_path)
                    success += 1
                else:
                    failed.append((mid, "no structure"))
            except Exception as e:
                failed.append((mid, str(e)))

    return success, failed


def load_material_ids_from_file(path):
    """Load material_id list from a text file, one per line; lines starting with # are comments."""
    ids = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.split("#")[0].strip()
            if line and line.startswith("mp-"):
                ids.append(line)
    return ids


def main():
    parser = argparse.ArgumentParser(
        description="Batch download CIF files from Materials Project",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Download by material_id list (IDs on command line)
  python download_mp_cifs.py --ids mp-149 mp-1234 -o ./my_cifs

  # Load material_id list from file (one per line)
  python download_mp_cifs.py --ids-file mp_ids.txt -o ./my_cifs

  # Query by elements (e.g. materials containing Si and O, max 500)
  python download_mp_cifs.py --elements Si O --max 500 -o ./cifs_sio

  # Download by chemical system
  python download_mp_cifs.py --chemsys Si-O --max 200 -o ./cifs_sio

  # Default: material contains at least one of S, Se, Te and energy above hull > 0.5 eV/atom
  python download_mp_cifs.py -o ./cifs_s_se_te
        """,
    )
    parser.add_argument(
        "--api-key",
        default=DEFAULT_API_KEY,
        help="Materials Project API Key; defaults to MP_API_KEY env or built-in value",
    )
    parser.add_argument(
        "-o", "--output",
        default="./cifs",
        help="Directory to save CIF files (default: ./cifs)",
    )
    parser.add_argument(
        "--no-skip",
        action="store_true",
        help="Do not skip existing CIFs; overwrite them",
    )
    parser.add_argument(
        "--ids",
        nargs="*",
        help="Material ID list, e.g.: --ids mp-149 mp-1234",
    )
    parser.add_argument(
        "--ids-file",
        help="Path to text file with material_id, one per line",
    )
    parser.add_argument(
        "--elements",
        nargs="+",
        help="Filter by elements, e.g.: --elements Si O",
    )
    parser.add_argument(
        "--formula",
        help="Filter by formula, e.g.: --formula SiO2",
    )
    parser.add_argument(
        "--chemsys",
        help="Filter by chemical system, e.g.: --chemsys Si-O",
    )
    parser.add_argument(
        "--eabove-hull",
        type=float,
        default=None,
        metavar="EV",
        help="Lower bound for energy above hull (eV/atom); keep only materials > EV; default 0.5 with default elements",
    )
    parser.add_argument(
        "--max",
        type=int,
        default=20000,
        help="Maximum number of entries when downloading by query (default 20000)",
    )

    args = parser.parse_args()
    skip_existing = not args.no_skip

    if args.ids or args.ids_file:
        material_ids = list(args.ids or [])
        if args.ids_file:
            material_ids.extend(load_material_ids_from_file(args.ids_file))
        if not material_ids:
            print("No material_id provided (--ids or --ids-file).")
            return
        print(f"Downloading {len(material_ids)} CIFs to {args.output} ...")
        success, failed = download_cifs_by_material_ids(
            material_ids,
            cif_dir=args.output,
            api_key=args.api_key,
            skip_existing=skip_existing,
        )
    elif args.elements or args.formula or args.chemsys:
        eabove = (args.eabove_hull, 1e6) if args.eabove_hull is not None else None
        print(f"Downloading CIFs by query to {args.output} (max {args.max}) ...")
        success, failed = download_cifs_by_query(
            elements=args.elements,
            formula=args.formula,
            chemsys=args.chemsys,
            energy_above_hull=eabove,
            max_results=args.max,
            cif_dir=args.output,
            api_key=args.api_key,
            skip_existing=skip_existing,
        )
    else:
        # Default: material contains at least one of S / Se / Te and energy above hull > 0.5 eV/atom
        eabove = (0.5, 1e6) if args.eabove_hull is None else (args.eabove_hull, 1e6)
        print(
            "Using default criteria: material contains at least one of S / Se / Te, "
            f"energy above hull > {eabove[0]} eV/atom"
        )
        print(f"Downloading CIFs by query to {args.output} (max {args.max}) ...")
        elements_groups = [["S"], ["Se"], ["Te"]]
        total_success = 0
        total_failed = []
        for grp in elements_groups:
            print(f"  Sub-query: element {grp[0]} ...")
            s, f = download_cifs_by_query(
                elements=grp,
                formula=None,
                chemsys=None,
                energy_above_hull=eabove,
                max_results=args.max,
                cif_dir=args.output,
                api_key=args.api_key,
                skip_existing=skip_existing,
            )
            total_success += s
            total_failed.extend(f)
        success, failed = total_success, total_failed

    print(f"Success: {success}, Failed: {len(failed)}")
    if failed:
        for mid, err in failed[:20]:
            print(f"  Failed {mid}: {err}")
        if len(failed) > 20:
            print(f"  ... and {len(failed) - 20} more failures")


if __name__ == "__main__":
    main()
