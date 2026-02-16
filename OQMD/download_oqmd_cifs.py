# -*- coding: utf-8 -*-
"""
Batch download CIF files from OQMD (Open Quantum Materials Database).
Uses OQMD REST API: http://oqmd.org/oqmdapi/
No API Key required. Optional dependencies: qmpy-rester or requests + pymatgen only.
"""

import os
import re
import argparse
import time
from pathlib import Path

try:
    import requests
except ImportError:
    requests = None

OQMD_API_BASE = "http://oqmd.org/oqmdapi/formationenergy"


def _parse_site(site_str):
    """Parse OQMD sites format: 'Element @ x y z' -> (element, [x, y, z])."""
    m = re.match(r"^\s*(\w+)\s+@\s+([\d.\-]+)\s+([\d.\-]+)\s+([\d.\-]+)\s*$", site_str.strip())
    if not m:
        return None
    el, x, y, z = m.group(1), float(m.group(2)), float(m.group(3)), float(m.group(4))
    return (el, [x, y, z])


def _oqmd_data_to_structure(unit_cell, sites_str_list):
    """Convert OQMD unit_cell (3x3) and sites list to pymatgen Structure."""
    from pymatgen.core import Lattice, Structure

    lattice = Lattice(unit_cell)
    species = []
    coords = []
    for s in sites_str_list:
        parsed = _parse_site(s) if isinstance(s, str) else None
        if parsed:
            species.append(parsed[0])
            coords.append(parsed[1])
    if not species:
        return None
    return Structure(lattice, species, coords, coords_are_cartesian=False)


def fetch_oqmd_structure_by_entry_id(entry_id, session=None):
    """
    Fetch a single structure (unit_cell + sites) from OQMD API by entry_id.

    Returns
    -------
    dict with keys: entry_id, name, unit_cell, sites ; or None if failed
    """
    if requests is None:
        raise RuntimeError("requests is required: pip install requests")
    session = session or requests.Session()
    url = (
        f"{OQMD_API_BASE}?fields=entry_id,name,unit_cell,sites"
        f"&format=json&limit=1&filter=entry_id={int(entry_id)}"
    )
    r = session.get(url, timeout=30)
    r.raise_for_status()
    data = r.json()
    recs = data.get("data") or []
    if not recs:
        return None
    rec = recs[0]
    if "unit_cell" not in rec or "sites" not in rec:
        return None
    return rec


def download_cifs_by_entry_ids(
    entry_ids,
    cif_dir="./cifs",
    skip_existing=True,
    delay=0.2,
):
    """
    Batch download CIFs by OQMD entry_id list.

    Parameters
    ----------
    entry_ids : list[int|str]
        OQMD entry_id list, e.g. [1216058, 16974]
    cif_dir : str
        Directory to save CIF files
    skip_existing : bool
        Whether to skip if target CIF already exists
    delay : float
        Delay in seconds between requests to avoid rate limiting

    Returns
    -------
    tuple (success_count, fail_list)
    """
    Path(cif_dir).mkdir(parents=True, exist_ok=True)
    success = 0
    failed = []
    session = requests.Session() if requests else None

    for eid in entry_ids:
        try:
            eid = int(eid)
        except (ValueError, TypeError):
            failed.append((str(eid), "invalid entry_id"))
            continue
        out_path = os.path.join(cif_dir, f"oqmd_{eid}.cif")
        if skip_existing and os.path.isfile(out_path):
            success += 1
            continue
        if delay > 0:
            time.sleep(delay)
        try:
            rec = fetch_oqmd_structure_by_entry_id(eid, session=session)
            if rec is None:
                failed.append((eid, "no data"))
                continue
            struct = _oqmd_data_to_structure(rec["unit_cell"], rec["sites"])
            if struct is None:
                failed.append((eid, "parse structure failed"))
                continue
            struct.to(fmt="cif", filename=out_path)
            success += 1
        except Exception as ex:
            failed.append((eid, str(ex)))

    return success, failed


def get_entry_ids_by_query(
    element_set=None,
    composition=None,
    stability=None,
    filter_expr=None,
    limit=500,
    offset=0,
):
    """
    Query OQMD by criteria and return list of entry_id.

    Parameters
    ----------
    element_set : str, optional
        e.g. "(Fe-Mn),O" for (Fe or Mn) and O
    composition : str, optional
        e.g. "Al2O3", "Fe-O"
    stability : str, optional
        e.g. "0", "<-0.1"
    filter_expr : str, optional
        Custom filter, e.g. "element_set=O AND stability<0"
    limit : int
        Number of results per request
    offset : int
        Offset for pagination

    Returns
    -------
    list[int]
    """
    if requests is None:
        raise RuntimeError("requests is required: pip install requests")
    params = ["format=json", "fields=entry_id", f"limit={int(limit)}", f"offset={int(offset)}"]
    if composition:
        params.append(f"composition={requests.utils.quote(composition)}")
    if filter_expr:
        params.append(f"filter={requests.utils.quote(filter_expr)}")
    else:
        parts = []
        if element_set:
            parts.append(f"element_set={element_set}")
        if stability is not None:
            parts.append(f"stability={stability}")
        if parts:
            params.append(f"filter={requests.utils.quote(' AND '.join(parts))}")
    url = f"{OQMD_API_BASE}?{'&'.join(params)}"
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    data = r.json()
    recs = data.get("data") or []
    return [int(r["entry_id"]) for r in recs if "entry_id" in r]


def download_cifs_by_query(
    element_set=None,
    composition=None,
    stability=None,
    filter_expr=None,
    max_results=500,
    cif_dir="./cifs",
    skip_existing=True,
    delay=0.2,
):
    """
    Query OQMD by element/composition/stability and download matching CIFs.

    Returns
    -------
    tuple (success_count, fail_list)
    """
    all_ids = []
    offset = 0
    chunk = min(500, max_results)
    while len(all_ids) < max_results:
        ids = get_entry_ids_by_query(
            element_set=element_set,
            composition=composition,
            stability=stability,
            filter_expr=filter_expr,
            limit=chunk,
            offset=offset,
        )
        if not ids:
            break
        all_ids.extend(ids)
        if len(ids) < chunk:
            break
        offset += chunk
        if len(all_ids) >= max_results:
            all_ids = all_ids[:max_results]
            break
        time.sleep(delay)
    return download_cifs_by_entry_ids(
        all_ids,
        cif_dir=cif_dir,
        skip_existing=skip_existing,
        delay=delay,
    )


def load_entry_ids_from_file(path):
    """Load entry_id list from text file, one per line; # starts a comment."""
    ids = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.split("#")[0].strip()
            if not line:
                continue
            try:
                ids.append(int(line))
            except ValueError:
                if line.isdigit():
                    ids.append(int(line))
    return ids


def main():
    parser = argparse.ArgumentParser(
        description="Batch download CIF files from OQMD",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Download by entry_id
  python download_oqmd_cifs.py --ids 1216058 16974 -o ./oqmd_cifs

  # Load entry_id list from file
  python download_oqmd_cifs.py --ids-file oqmd_ids.txt -o ./oqmd_cifs

  # Query by elements ((Fe or Mn) and O, max 200)
  python download_oqmd_cifs.py --element-set "(Fe-Mn),O" --max 200 -o ./oqmd_cifs

  # By composition and stability
  python download_oqmd_cifs.py --composition Fe-O --stability 0 --max 100 -o ./oqmd_cifs

  # Default: S, Se, Te and energy above hull (stability) > 0.5 eV/atom
  python download_oqmd_cifs.py -o ./oqmd_s_se_te
        """,
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
        "--delay",
        type=float,
        default=0.2,
        help="Delay in seconds between API requests (default 0.2)",
    )
    parser.add_argument("--ids", nargs="*", help="Entry ID list, e.g.: --ids 1216058 16974")
    parser.add_argument("--ids-file", help="Path to text file with entry_id, one per line")
    parser.add_argument(
        "--element-set",
        help='Element set, e.g. "(Fe-Mn),O" for (Fe or Mn) and O',
    )
    parser.add_argument("--composition", help="Composition or phase space, e.g. Al2O3, Fe-O")
    parser.add_argument("--stability", help="Stability (hull distance), e.g. 0, <-0.1")
    parser.add_argument("--filter", dest="filter_expr", help="Custom filter expression")
    parser.add_argument(
        "--max",
        type=int,
        default=20000,
        help="Maximum number of entries when downloading by query (default 20000)",
    )

    args = parser.parse_args()
    skip_existing = not args.no_skip

    if args.ids or args.ids_file:
        entry_ids = list(args.ids or [])
        if args.ids_file:
            entry_ids.extend(load_entry_ids_from_file(args.ids_file))
        if not entry_ids:
            print("No entry_id provided (--ids or --ids-file).")
            return
        print(f"Downloading {len(entry_ids)} CIFs to {args.output} ...")
        success, failed = download_cifs_by_entry_ids(
            entry_ids,
            cif_dir=args.output,
            skip_existing=skip_existing,
            delay=args.delay,
        )
    elif args.element_set or args.composition or args.stability is not None or args.filter_expr:
        print(f"Downloading CIFs by query to {args.output} (max {args.max}) ...")
        success, failed = download_cifs_by_query(
            element_set=args.element_set,
            composition=args.composition,
            stability=args.stability,
            filter_expr=args.filter_expr,
            max_results=args.max,
            cif_dir=args.output,
            skip_existing=skip_existing,
            delay=args.delay,
        )
    else:
        # Default: S, Se, Te (any) and energy above hull (stability) > 0.5 eV/atom
        print("Using default criteria: elements S, Se, Te (any), stability (energy above hull) > 0.5 eV/atom")
        print(f"Downloading CIFs by query to {args.output} (max {args.max}) ...")
        success, failed = download_cifs_by_query(
            element_set=None,
            composition=None,
            stability=None,
            filter_expr="element_set=(S-Se-Te) AND stability>0.5",
            max_results=args.max,
            cif_dir=args.output,
            skip_existing=skip_existing,
            delay=args.delay,
        )

    print(f"Success: {success}, Failed: {len(failed)}")
    if failed:
        for eid, err in failed[:20]:
            print(f"  Failed {eid}: {err}")
        if len(failed) > 20:
            print(f"  ... and {len(failed) - 20} more failures")


if __name__ == "__main__":
    main()
