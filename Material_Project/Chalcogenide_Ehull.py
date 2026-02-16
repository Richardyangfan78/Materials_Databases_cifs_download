import os
import argparse
from pathlib import Path

DEFAULT_API_KEY = os.environ.get("MP_API_KEY", "8i00vBC1hXg3nVo0t0QvPbSd1GVbz9si")


def download_cifs_by_material_ids(
    material_ids,
    cif_dir="./cifs",
    api_key=DEFAULT_API_KEY,
    skip_existing=True,
):
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


def download_cifs_by_query_sorted(
    elements=None,
    formula=None,
    chemsys=None,
    max_results=20000,
    base_dir="./cifs",
    dir_eq_zero="ehull_eq_0",
    dir_lt_half="ehull_lt_0.5",
    dir_gt_half="ehull_gt_0.5",
    api_key=DEFAULT_API_KEY,
    skip_existing=True,
):
    """
    Query Materials Project and sort results into three folders
    based on energy_above_hull:
      - ehull == 0          -> base_dir/dir_eq_zero/
      - 0 < ehull < 0.5     -> base_dir/dir_lt_half/
      - ehull >= 0.5         -> base_dir/dir_gt_half/
    """
    from mp_api.client import MPRester

    path_eq = os.path.join(base_dir, dir_eq_zero)
    path_lt = os.path.join(base_dir, dir_lt_half)
    path_gt = os.path.join(base_dir, dir_gt_half)
    for p in [path_eq, path_lt, path_gt]:
        Path(p).mkdir(parents=True, exist_ok=True)

    counts = {"eq_zero": 0, "lt_half": 0, "gt_half": 0}
    failed = []

    chunk_size = min(1000, max_results)
    num_chunks = max(1, (max_results + chunk_size - 1) // chunk_size)

    search_kw = dict(
        elements=elements,
        formula=formula,
        chemsys=chemsys,
        fields=["material_id", "structure", "energy_above_hull"],
        chunk_size=chunk_size,
        num_chunks=num_chunks,
    )

    with MPRester(api_key) as mpr:
        docs = list(mpr.materials.summary.search(**search_kw))
        print(f"    Fetched {len(docs)} entries from API")
        for doc in docs:
            mid = str(doc.material_id)
            ehull = getattr(doc, "energy_above_hull", None)

            # Determine target folder
            if ehull is not None and ehull == 0:
                target_dir = path_eq
                bucket = "eq_zero"
            elif ehull is not None and ehull < 0.5:
                target_dir = path_lt
                bucket = "lt_half"
            else:
                target_dir = path_gt
                bucket = "gt_half"

            out_path = os.path.join(target_dir, f"{mid}.cif")
            if skip_existing and os.path.isfile(out_path):
                counts[bucket] += 1
                continue
            try:
                if getattr(doc, "structure", None) is not None:
                    doc.structure.to(fmt="cif", filename=out_path)
                    counts[bucket] += 1
                else:
                    failed.append((mid, "no structure"))
            except Exception as e:
                failed.append((mid, str(e)))

    return counts, failed


def load_material_ids_from_file(path):
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
    )
    parser.add_argument(
        "--api-key",
        default=DEFAULT_API_KEY,
    )
    parser.add_argument(
        "-o", "--output",
        default="./cifs",
    )
    parser.add_argument(
        "--no-skip",
        action="store_true",
    )
    parser.add_argument(
        "--ids",
        nargs="*",
    )
    parser.add_argument(
        "--ids-file",
    )
    parser.add_argument(
        "--elements",
        nargs="+",
    )
    parser.add_argument(
        "--formula",
    )
    parser.add_argument(
        "--chemsys",
    )
    parser.add_argument(
        "--eabove-hull",
        type=float,
        default=None,
        metavar="EV",
    )
    parser.add_argument(
        "--max",
        type=int,
        default=20000,
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
        print(f"Success: {success}, Failed: {len(failed)}")
    elif args.elements or args.formula or args.chemsys:
        eabove = (args.eabove_hull, 1e6) if args.eabove_hull is not None else None
        print(f"Downloading CIFs to {args.output} (max {args.max}) ...")
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
        print(f"Success: {success}, Failed: {len(failed)}")
    else:
        # Default: download all compounds containing S, Se, or Te,
        # sorted into three folders by energy_above_hull.
        print(
            "Default mode: downloading all compounds containing S / Se / Te\n"
            "Sorting into 3 folders:\n"
            f"  {args.output}/ehull_eq_0/     -> energy_above_hull == 0\n"
            f"  {args.output}/ehull_lt_0.5/   -> 0 < energy_above_hull < 0.5\n"
            f"  {args.output}/ehull_gt_0.5/   -> energy_above_hull >= 0.5\n"
        )
        elements_groups = [["S"], ["Se"], ["Te"]]
        total_counts = {"eq_zero": 0, "lt_half": 0, "gt_half": 0}
        total_failed = []

        for grp in elements_groups:
            elem = grp[0]
            print(f"  Sub-query: element {elem} (max {args.max}) ...")
            counts, failed = download_cifs_by_query_sorted(
                elements=grp,
                max_results=args.max,
                base_dir=args.output,
                api_key=args.api_key,
                skip_existing=skip_existing,
            )
            for k in total_counts:
                total_counts[k] += counts[k]
            total_failed.extend(failed)

        total = sum(total_counts.values())
        print(f"\n{'='*50}")
        print(f"Download complete. Total success: {total}, Failed: {len(total_failed)}")
        print(f"  ehull == 0      : {total_counts['eq_zero']}")
        print(f"  0 < ehull < 0.5 : {total_counts['lt_half']}")
        print(f"  ehull >= 0.5    : {total_counts['gt_half']}")
        failed = total_failed

    if failed:
        print(f"\nFailed entries:")
        for mid, err in failed[:20]:
            print(f"  {mid}: {err}")
        if len(failed) > 20:
            print(f"  ... {len(failed) - 20} more failures")


if __name__ == "__main__":
    main()