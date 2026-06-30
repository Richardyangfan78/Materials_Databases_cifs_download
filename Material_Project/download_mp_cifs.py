# -*- coding: utf-8 -*-
"""
Download a Materials Project chalcohalide dataset.

Dataset definition
------------------
The default query collects MP structures containing at least one chalcogen
element Ch in {S, Se, Te}, at least one halide element X in {Cl, Br, I}, and
at least one metal or metalloid cation. For each retained structure the script
writes the CIF and a metadata CSV with:

    Eg    Band gap from MP summary.band_gap
    GT    Gap type: direct, indirect, metal, or unknown
    Ehull Energy above hull from MP summary.energy_above_hull
    TS    Thermodynamic stability label, 1 if Ehull <= 0.1 eV/atom else 0

API Key can be obtained from https://www.materialsproject.org/dashboard.
It is recommended to set the API Key via the MP_API_KEY environment variable.
"""

import argparse
import csv
import os
from pathlib import Path


DEFAULT_API_KEY = os.environ.get("MP_API_KEY", "8i00vBC1hXg3nVo0t0QvPbSd1GVbz9si")

CHALCOGENS = ("S", "Se", "Te")
HALIDES = ("Cl", "Br", "I")
METALLOIDS = {"B", "Si", "Ge", "As", "Sb"}
METALS = {
    "Li",
    "Be",
    "Na",
    "Mg",
    "Al",
    "K",
    "Ca",
    "Sc",
    "Ti",
    "V",
    "Cr",
    "Mn",
    "Fe",
    "Co",
    "Ni",
    "Cu",
    "Zn",
    "Ga",
    "Rb",
    "Sr",
    "Y",
    "Zr",
    "Nb",
    "Mo",
    "Tc",
    "Ru",
    "Rh",
    "Pd",
    "Ag",
    "Cd",
    "In",
    "Sn",
    "Cs",
    "Ba",
    "La",
    "Ce",
    "Pr",
    "Nd",
    "Pm",
    "Sm",
    "Eu",
    "Gd",
    "Tb",
    "Dy",
    "Ho",
    "Er",
    "Tm",
    "Yb",
    "Lu",
    "Hf",
    "Ta",
    "W",
    "Re",
    "Os",
    "Ir",
    "Pt",
    "Au",
    "Hg",
    "Tl",
    "Pb",
    "Bi",
    "Po",
    "Fr",
    "Ra",
    "Ac",
    "Th",
    "Pa",
    "U",
    "Np",
    "Pu",
    "Am",
    "Cm",
    "Bk",
    "Cf",
    "Es",
    "Fm",
    "Md",
    "No",
    "Lr",
    "Rf",
    "Db",
    "Sg",
    "Bh",
    "Hs",
    "Mt",
    "Ds",
    "Rg",
    "Cn",
    "Nh",
    "Fl",
    "Mc",
    "Lv",
}
CATION_ELEMENTS = (METALS | METALLOIDS) - set(CHALCOGENS) - set(HALIDES)

SUMMARY_FIELDS = [
    "material_id",
    "formula_pretty",
    "elements",
    "structure",
    "band_gap",
    "is_gap_direct",
    "is_metal",
    "energy_above_hull",
]
FALLBACK_SUMMARY_FIELDS = [
    "material_id",
    "formula_pretty",
    "elements",
    "structure",
    "band_gap",
    "energy_above_hull",
]
METADATA_COLUMNS = [
    "material_id",
    "formula_pretty",
    "elements",
    "chalcogens",
    "halides",
    "cations",
    "Eg",
    "GT",
    "Ehull",
    "TS",
    "TS_label",
    "cif_path",
]


def _summary_fields(include_structure):
    fields = list(SUMMARY_FIELDS)
    if not include_structure:
        fields.remove("structure")
    return fields


def _fallback_summary_fields(include_structure):
    fields = list(FALLBACK_SUMMARY_FIELDS)
    if not include_structure:
        fields.remove("structure")
    return fields


def _doc_value(doc, name, default=None):
    if hasattr(doc, name):
        return getattr(doc, name)
    if isinstance(doc, dict):
        return doc.get(name, default)
    return default


def _symbol(element):
    return getattr(element, "symbol", str(element))


def _symbols_from_doc(doc):
    elements = _doc_value(doc, "elements")
    if elements:
        return sorted({_symbol(el) for el in elements})

    structure = _doc_value(doc, "structure")
    if structure is not None:
        return sorted({_symbol(el) for el in structure.composition.elements})

    return []


def _material_sort_key(material_id):
    text = str(material_id)
    if text.startswith("mp-"):
        suffix = text[3:]
        if suffix.isdigit():
            return (0, int(suffix))
    return (1, text)


def _chunk_options(max_results):
    if max_results is None or max_results <= 0:
        return {"chunk_size": 1000}

    chunk_size = min(1000, max_results)
    num_chunks = max(1, (max_results + chunk_size - 1) // chunk_size)
    return {"chunk_size": chunk_size, "num_chunks": num_chunks}


def _search_summary(mpr, *, elements, max_results, include_structure):
    search_kw = {
        "elements": elements,
        "fields": _summary_fields(include_structure),
        **_chunk_options(max_results),
    }

    try:
        docs = list(mpr.materials.summary.search(**search_kw))
    except Exception as exc:
        print(
            "    Full MP field query failed; retrying without optional gap fields. "
            f"Reason: {exc}"
        )
        search_kw["fields"] = _fallback_summary_fields(include_structure)
        docs = list(mpr.materials.summary.search(**search_kw))

    if max_results is not None and max_results > 0:
        return docs[:max_results]
    return docs


def _is_chalcohalide_candidate(symbols):
    symbol_set = set(symbols)
    chalcogens = sorted(symbol_set & set(CHALCOGENS))
    halides = sorted(symbol_set & set(HALIDES))
    cations = sorted(symbol_set & CATION_ELEMENTS)
    return bool(chalcogens and halides and cations), chalcogens, halides, cations


def _gap_type(eg, is_gap_direct, is_metal):
    if is_metal is True:
        return "metal"
    if eg is not None and eg <= 1e-8:
        return "metal"
    if is_gap_direct is True:
        return "direct"
    if is_gap_direct is False:
        return "indirect"
    return "unknown"


def _stability_label(ehull, stable_threshold):
    if ehull is None:
        return "", "unknown"
    if ehull <= stable_threshold:
        return 1, "stable"
    return 0, "unstable"


def _record_from_doc(doc, *, cif_path, stable_threshold):
    symbols = _symbols_from_doc(doc)
    _, chalcogens, halides, cations = _is_chalcohalide_candidate(symbols)

    eg = _doc_value(doc, "band_gap")
    ehull = _doc_value(doc, "energy_above_hull")
    ts, ts_label = _stability_label(ehull, stable_threshold)

    return {
        "material_id": str(_doc_value(doc, "material_id")),
        "formula_pretty": _doc_value(doc, "formula_pretty", ""),
        "elements": ";".join(symbols),
        "chalcogens": ";".join(chalcogens),
        "halides": ";".join(halides),
        "cations": ";".join(cations),
        "Eg": eg,
        "GT": _gap_type(
            eg,
            _doc_value(doc, "is_gap_direct"),
            _doc_value(doc, "is_metal"),
        ),
        "Ehull": ehull,
        "TS": ts,
        "TS_label": ts_label,
        "cif_path": str(cif_path),
    }


def write_metadata_csv(records, metadata_path):
    Path(metadata_path).parent.mkdir(parents=True, exist_ok=True)
    with open(metadata_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=METADATA_COLUMNS)
        writer.writeheader()
        for record in records:
            writer.writerow(record)


def download_cifs_by_material_ids(
    material_ids,
    cif_dir="./cifs",
    api_key=DEFAULT_API_KEY,
    skip_existing=True,
):
    """
    Batch download CIFs by material_id list from Materials Project.
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


def download_chalcohalide_dataset(
    output_dir="./mp_chalcohalides",
    metadata_filename="chalcohalide_metadata.csv",
    api_key=DEFAULT_API_KEY,
    max_results_per_pair=0,
    stable_threshold=0.1,
    skip_existing=True,
    write_cifs=True,
):
    """
    Query MP for chalcohalides, save CIFs, and write target-property metadata.

    Parameters
    ----------
    output_dir : str
        Base output directory.
    metadata_filename : str
        Metadata CSV filename. Relative paths are resolved under output_dir.
    api_key : str
        Materials Project API key.
    max_results_per_pair : int
        Maximum MP results per Ch-X pair. Use 0 or negative for all available
        results returned by the API.
    stable_threshold : float
        Ehull threshold for TS positive class, in eV/atom.
    skip_existing : bool
        Whether to skip writing existing CIF files.
    write_cifs : bool
        If False, only metadata is written.
    """
    from mp_api.client import MPRester

    output_path = Path(output_dir)
    cif_dir = output_path / "cifs"
    metadata_path = Path(metadata_filename)
    if not metadata_path.is_absolute():
        metadata_path = output_path / metadata_path

    if write_cifs:
        cif_dir.mkdir(parents=True, exist_ok=True)
    metadata_path.parent.mkdir(parents=True, exist_ok=True)

    docs_by_id = {}
    query_counts = {}

    with MPRester(api_key) as mpr:
        for ch in CHALCOGENS:
            for halide in HALIDES:
                pair = [ch, halide]
                print(f"  Querying MP for {ch}-{halide} compounds ...")
                docs = _search_summary(
                    mpr,
                    elements=pair,
                    max_results=max_results_per_pair,
                    include_structure=write_cifs,
                )
                query_counts[f"{ch}-{halide}"] = len(docs)
                print(f"    Retrieved {len(docs)} entries")

                for doc in docs:
                    material_id = str(_doc_value(doc, "material_id"))
                    symbols = _symbols_from_doc(doc)
                    keep, _, _, _ = _is_chalcohalide_candidate(symbols)
                    if keep and material_id not in docs_by_id:
                        docs_by_id[material_id] = doc

    records = []
    failed = []
    cif_success = 0

    for material_id in sorted(docs_by_id, key=_material_sort_key):
        doc = docs_by_id[material_id]
        cif_path = cif_dir / f"{material_id}.cif"

        if write_cifs:
            if skip_existing and cif_path.is_file():
                cif_success += 1
            else:
                try:
                    structure = _doc_value(doc, "structure")
                    if structure is None:
                        failed.append((material_id, "no structure"))
                    else:
                        structure.to(fmt="cif", filename=str(cif_path))
                        cif_success += 1
                except Exception as exc:
                    failed.append((material_id, str(exc)))

        records.append(
            _record_from_doc(
                doc,
                cif_path=cif_path if write_cifs else "",
                stable_threshold=stable_threshold,
            )
        )

    write_metadata_csv(records, metadata_path)

    return {
        "records": len(records),
        "cif_success": cif_success,
        "failed": failed,
        "metadata_path": str(metadata_path),
        "cif_dir": str(cif_dir) if write_cifs else "",
        "query_counts": query_counts,
    }


def load_material_ids_from_file(path):
    """Load material_id list from a text file, one per line."""
    ids = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.split("#")[0].strip()
            if line and line.startswith("mp-"):
                ids.append(line)
    return ids


def main():
    parser = argparse.ArgumentParser(
        description="Download Materials Project chalcohalide CIFs and labels",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Default chalcohalide dataset:
  python download_mp_cifs.py -o ./mp_chalcohalides

  # Dry metadata-style query without writing CIFs:
  python download_mp_cifs.py -o ./mp_chalcohalides --no-cifs

  # Limit each Ch-X sub-query during testing:
  python download_mp_cifs.py --max 100 -o ./mp_chalcohalides_test

  # Download only selected Materials Project IDs:
  python download_mp_cifs.py --ids mp-149 mp-1234 -o ./selected_cifs
        """,
    )
    parser.add_argument(
        "--api-key",
        default=DEFAULT_API_KEY,
        help="Materials Project API Key; defaults to MP_API_KEY env or built-in value",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="./mp_chalcohalides",
        help="Output directory (default: ./mp_chalcohalides)",
    )
    parser.add_argument(
        "--metadata",
        default="chalcohalide_metadata.csv",
        help="Metadata CSV path or filename (default: chalcohalide_metadata.csv)",
    )
    parser.add_argument(
        "--stable-threshold",
        type=float,
        default=0.1,
        help="Ehull threshold for TS=1 stable label in eV/atom (default: 0.1)",
    )
    parser.add_argument(
        "--max",
        type=int,
        default=0,
        help="Maximum results per Ch-X query; 0 means all available (default: 0)",
    )
    parser.add_argument(
        "--no-cifs",
        action="store_true",
        help="Write metadata only; do not save CIF files",
    )
    parser.add_argument(
        "--no-skip",
        action="store_true",
        help="Do not skip existing CIFs; overwrite them",
    )
    parser.add_argument(
        "--ids",
        nargs="*",
        help="Legacy mode: download CIFs for explicit material IDs",
    )
    parser.add_argument(
        "--ids-file",
        help="Legacy mode: text file with one material_id per line",
    )

    args = parser.parse_args()
    skip_existing = not args.no_skip

    if args.ids is not None or args.ids_file:
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
    else:
        print(
            "Default mode: MP chalcohalide dataset\n"
            f"  Ch = {', '.join(CHALCOGENS)}\n"
            f"  X  = {', '.join(HALIDES)}\n"
            "  cation filter = at least one metal/metalloid element\n"
            f"  TS positive class = Ehull <= {args.stable_threshold} eV/atom\n"
        )
        result = download_chalcohalide_dataset(
            output_dir=args.output,
            metadata_filename=args.metadata,
            api_key=args.api_key,
            max_results_per_pair=args.max,
            stable_threshold=args.stable_threshold,
            skip_existing=skip_existing,
            write_cifs=not args.no_cifs,
        )
        failed = result["failed"]
        print(f"\n{'=' * 60}")
        print(f"Dataset records: {result['records']}")
        if not args.no_cifs:
            print(f"CIF files written/skipped: {result['cif_success']}")
            print(f"CIF directory: {result['cif_dir']}")
        print(f"Metadata CSV: {result['metadata_path']}")
        print(f"Failed CIF writes: {len(failed)}")

    if failed:
        print("\nFailed entries:")
        for mid, err in failed[:20]:
            print(f"  {mid}: {err}")
        if len(failed) > 20:
            print(f"  ... {len(failed) - 20} more failures")


if __name__ == "__main__":
    main()
