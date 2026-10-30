"""Local data access for the prototype's structured records."""

import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def _read_json(filename):
    with (DATA_DIR / filename).open(encoding="utf-8") as stream:
        return json.load(stream)


def get_policies():
    return _read_json("policies.json")


def get_branches():
    return _read_json("branches.json")


def get_occupations():
    return _read_json("occupations.json")


def get_market_reference():
    return _read_json("market_reference.json")
