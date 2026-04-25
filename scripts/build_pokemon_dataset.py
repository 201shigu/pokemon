#!/usr/bin/env python3
import argparse
import csv
import gzip
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

import urllib.request
import urllib.error

SMOGON_MONTH = "2026-03"
FORMAT = "gen9ou"
TOP_N = 120
MIN_MOVE_USAGE = 1.0

USAGE_URL = f"https://www.smogon.com/stats/{SMOGON_MONTH}/{FORMAT}-0.txt"
MOVESET_URL = f"https://www.smogon.com/stats/{SMOGON_MONTH}/moveset/{FORMAT}-0.txt"
POKEAPI_POKEMON = "https://pokeapi.co/api/v2/pokemon/{name}"
POKEAPI_ABILITY = "https://pokeapi.co/api/v2/ability/{name}"

USER_AGENT = "pokemon-champions-dataset-builder/1.0"


@dataclass
class UsageEntry:
    rank: int
    name: str
    usage_percent: float


def http_get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            return res.read()
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP error while fetching {url}: {e.code} {e.reason}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Network error while fetching {url}: {e.reason}") from e


def fetch_text(url: str) -> str:
    body = http_get(url)
    if url.endswith(".gz"):
        return gzip.decompress(body).decode("utf-8", errors="replace")
    return body.decode("utf-8", errors="replace")


def parse_usage(text: str, top_n: int) -> List[UsageEntry]:
    entries: List[UsageEntry] = []
    pattern = re.compile(r"^\|\s*(\d+)\s*\|\s*([^|]+?)\s*\|\s*([\d.]+)%")
    for line in text.splitlines():
        m = pattern.match(line)
        if not m:
            continue
        rank = int(m.group(1))
        name = m.group(2).strip()
        usage = float(m.group(3))
        entries.append(UsageEntry(rank, name, usage))
        if len(entries) >= top_n:
            break
    return entries


def parse_moveset_sections(text: str) -> Dict[str, Dict[str, float]]:
    sections: Dict[str, Dict[str, float]] = {}
    blocks = text.split("\n +----------------------------------------+ \n")
    mon_header = re.compile(r"^\|\s*(.+?)\s*\|$")
    move_line = re.compile(r"^\|\s*([A-Za-z0-9'\- .:]+)\s+\|\s*([\d.]+)%\s*\|$")

    for block in blocks:
        lines = block.splitlines()
        if not lines:
            continue
        mon_name = None
        move_mode = False
        moves: Dict[str, float] = {}
        for line in lines:
            if mon_name is None:
                mh = mon_header.match(line)
                if mh and mh.group(1).strip() not in {"Raw count", "Avg. weight"}:
                    possible = mh.group(1).strip()
                    if possible and not possible.startswith("+") and not possible.startswith("-"):
                        mon_name = possible
                continue

            if "| Moves" in line:
                move_mode = True
                continue
            if move_mode and line.strip().startswith("+----------------------------------------+"):
                break
            if move_mode:
                mm = move_line.match(line)
                if mm:
                    move_name = mm.group(1).strip()
                    usage = float(mm.group(2))
                    if usage >= MIN_MOVE_USAGE:
                        moves[move_name] = usage
        if mon_name and moves:
            sections[mon_name] = moves
    return sections


def smogon_to_pokeapi_name(name: str) -> str:
    s = name.lower()
    s = s.replace(" ", "-")
    s = s.replace(".", "")
    replacements = {
        "nidoran-m": "nidoran-m",
        "nidoran-f": "nidoran-f",
        "farfetch'd": "farfetchd",
        "sirfetch'd": "sirfetchd",
        "mr-mime": "mr-mime",
        "mr-rime": "mr-rime",
        "type:-null": "type-null",
        "wo-chien": "wo-chien",
        "chien-pao": "chien-pao",
        "ting-lu": "ting-lu",
        "chi-yu": "chi-yu",
        "great-tusk": "great-tusk",
        "scream-tail": "scream-tail",
        "brute-bonnet": "brute-bonnet",
        "flutter-mane": "flutter-mane",
        "slither-wing": "slither-wing",
        "sandy-shocks": "sandy-shocks",
        "iron-treads": "iron-treads",
        "iron-bundle": "iron-bundle",
        "iron-hands": "iron-hands",
        "iron-jugulis": "iron-jugulis",
        "iron-moth": "iron-moth",
        "iron-thorns": "iron-thorns",
        "iron-valiant": "iron-valiant",
        "walking-wake": "walking-wake",
        "gouging-fire": "gouging-fire",
        "raging-bolt": "raging-bolt",
        "iron-boulder": "iron-boulder",
        "iron-crown": "iron-crown",
        "ursaluna-bloodmoon": "ursaluna-bloodmoon",
        "ogerpon-wellspring": "ogerpon-wellspring-mask",
        "ogerpon-hearthflame": "ogerpon-hearthflame-mask",
        "ogerpon-cornerstone": "ogerpon-cornerstone-mask",
        "ogerpon": "ogerpon",
        "landorus-therian": "landorus-therian",
        "tornadus-therian": "tornadus-therian",
        "thundurus-therian": "thundurus-therian",
        "enamorus-therian": "enamorus-therian",
        "necrozma-dusk-mane": "necrozma-dusk",
        "necrozma-dawn-wings": "necrozma-dawn",
        "deoxys-speed": "deoxys-speed",
        "deoxys-defense": "deoxys-defense",
        "deoxys-attack": "deoxys-attack",
        "zygarde-10%": "zygarde-10",
        "zygarde-complete": "zygarde-complete",
        "palafin-hero": "palafin-hero",
        "basculegion-f": "basculegion-female",
        "indeedee-f": "indeedee-female",
        "meowstic-f": "meowstic-female",
        "toxtricity-low-key": "toxtricity-low-key",
        "urshifu-rapid-strike": "urshifu-rapid-strike",
        "urshifu-single-strike": "urshifu-single-strike",
    }
    return replacements.get(s, s)


def get_pokemon_data(name: str) -> dict:
    api_name = smogon_to_pokeapi_name(name)
    url = POKEAPI_POKEMON.format(name=api_name)
    try:
        body = http_get(url)
    except RuntimeError as e:
        if " 404 " in str(e) and api_name.endswith("-totem"):
            api_name = api_name.replace("-totem", "")
            body = http_get(POKEAPI_POKEMON.format(name=api_name))
        else:
            raise
    return json.loads(body.decode("utf-8"))


def get_ability_effect(ability_name: str, cache: Dict[str, dict]) -> Tuple[str, List[str]]:
    if ability_name not in cache:
        body = http_get(POKEAPI_ABILITY.format(name=ability_name))
        cache[ability_name] = json.loads(body.decode("utf-8"))

    data = cache[ability_name]
    effect = ""
    for entry in data.get("effect_entries", []):
        if entry.get("language", {}).get("name") == "en":
            effect = entry.get("short_effect") or entry.get("effect") or ""
            break
    formulas = extract_formulas(effect)
    return effect, formulas


def extract_formulas(effect_text: str) -> List[str]:
    found: List[str] = []
    for pct in re.findall(r"(\d+)%", effect_text):
        found.append(f"p={pct}/100")
    for mult in re.findall(r"([0-9]+(?:\.[0-9]+)?)x", effect_text):
        found.append(f"multiplier={mult}")
    for frac in re.findall(r"(1/\d+)", effect_text):
        found.append(f"fraction={frac}")
    for stage in re.findall(r"([+-]\d+) stage", effect_text):
        found.append(f"stat_stage_change={stage}")
    return sorted(set(found))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build top-N competitive Pokémon dataset")
    parser.add_argument("--output-dir", default="data", help="Directory for generated JSON/CSV")
    parser.add_argument("--top-n", type=int, default=TOP_N, help="How many Pokémon to keep from usage table")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        usage_text = fetch_text(USAGE_URL)
        moveset_text = fetch_text(MOVESET_URL)
    except RuntimeError as e:
        raise SystemExit(
            "Failed to download source data. "
            "If you are in a restricted network, run this script where outbound HTTPS is allowed.\n"
            f"Detail: {e}"
        )

    usage_entries = parse_usage(usage_text, args.top_n)
    movesets = parse_moveset_sections(moveset_text)

    ability_cache: Dict[str, dict] = {}
    rows: List[dict] = []

    for entry in usage_entries:
        p = get_pokemon_data(entry.name)

        stats = {s["stat"]["name"]: s["base_stat"] for s in p["stats"]}

        abilities = []
        for ab in p["abilities"]:
            ab_name = ab["ability"]["name"]
            effect, formulas = get_ability_effect(ab_name, ability_cache)
            abilities.append(
                {
                    "name": ab_name,
                    "is_hidden": ab["is_hidden"],
                    "slot": ab["slot"],
                    "effect_text": effect,
                    "formula_tokens": formulas,
                }
            )

        move_candidates = movesets.get(entry.name, {})
        top_moves = sorted(move_candidates.items(), key=lambda x: x[1], reverse=True)[:10]

        rows.append(
            {
                "rank": entry.rank,
                "pokemon": entry.name,
                "usage_percent": entry.usage_percent,
                "types": [t["type"]["name"] for t in sorted(p["types"], key=lambda x: x["slot"])],
                "base_stats": stats,
                "abilities": abilities,
                "major_moves": [
                    {"name": move_name, "usage_percent": move_usage}
                    for move_name, move_usage in top_moves
                ],
                "sources": {
                    "usage": USAGE_URL,
                    "moves": MOVESET_URL,
                    "pokemon_api": POKEAPI_POKEMON.format(name=smogon_to_pokeapi_name(entry.name)),
                },
            }
        )

    json_path = output_dir / "top120_pokemon_dataset_2026-03_gen9ou.json"
    csv_path = output_dir / "top120_pokemon_dataset_2026-03_gen9ou.csv"

    with json_path.open("w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)

    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "rank",
                "pokemon",
                "usage_percent",
                "types",
                "hp",
                "attack",
                "defense",
                "special-attack",
                "special-defense",
                "speed",
                "abilities_json",
                "major_moves_json",
            ]
        )
        for row in rows:
            bs = row["base_stats"]
            writer.writerow(
                [
                    row["rank"],
                    row["pokemon"],
                    row["usage_percent"],
                    "/".join(row["types"]),
                    bs.get("hp"),
                    bs.get("attack"),
                    bs.get("defense"),
                    bs.get("special-attack"),
                    bs.get("special-defense"),
                    bs.get("speed"),
                    json.dumps(row["abilities"], ensure_ascii=False),
                    json.dumps(row["major_moves"], ensure_ascii=False),
                ]
            )

    print(f"Built dataset with {len(rows)} Pokémon")
    print(f"JSON: {json_path}")
    print(f"CSV : {csv_path}")


if __name__ == "__main__":
    main()
