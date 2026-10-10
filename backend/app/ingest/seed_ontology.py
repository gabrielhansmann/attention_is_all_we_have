"""Seed the ontology: top-level domains, vehicle lines, markets, and the customer-feedback
category labels (feedback_raw.vfc_level2) as children of the domains.

The label -> domain mapping is classified by an OpenAI chat model; review the output (the script
prints a sample and any 'unmapped' labels) and edit the table if needed. Idempotent.
Usage:  python -m app.ingest.seed_ontology
"""
import json
import os
import re

import psycopg
from app.config import load_env
from openai import OpenAI

load_env()
CHAT_MODEL = os.environ.get("OPENAI_CHAT_MODEL", "gpt-4o-mini")

DOMAINS = {  # docs/architecture/08-scaling-and-config.md
    "exterior": "Exterior", "interior": "Interior", "powertrain": "Powertrain",
    "driver_assistance": "Driver Assistance", "infotainment": "Infotainment",
    "comfort_space": "Comfort & Space", "usability": "Usability", "variant_package": "Variant & Package",
    "range_charging": "Range & Charging",
    "safety": "Safety (out of scope: regulatory/homologation)",
}
LINES = {"F70": "F70 (1 Series)", "G60": "G60 (5 Series)", "G68": "G68 (5 Series, China)", "G70": "G70 (7 Series)"}
MARKETS = {"EU": "Europe", "CN": "China", "US": "USA", "RoW": "Rest of World"}
SKIP = {"no_class_found"}

# Hand-assigned labels; these win over the model. Left unmapped on purpose: Owner's Manual,
# General enquiry: customer feedback, Caring Car (not about the vehicle itself).
OVERRIDES = {
    "Handling / Riding": "powertrain", "ground\xa0clearance": "powertrain", "RSC tire": "exterior",
    "Accessories / Parts": "variant_package",
    "Driver's Guide App": "infotainment", "My BMW / MINI Portal": "infotainment",
    "My BMW App / MINI App": "infotainment", "Personal eSIM": "infotainment",
    "Customer Account (My BMW / MINI Portal)": "infotainment",
    "Remote 3D View (My BMW App / MINI App)": "infotainment",
    "Remote Engine Start (My BMW App / MINI App)": "infotainment",
    "Remote Engine Start (Vehicle Key )": "usability",
    "Remote interior camera (My BMW App / MINI App)": "infotainment",
    "Remote Services & Remote Keyless Entry (My BMW App/MINI App)": "infotainment",
    "Hood, open / close": "usability", "Fuel filler flap , open / close": "usability",
    "Side window, open / close": "usability", "Light switch operating unit": "usability",
    "Wash / wipe switch": "usability", "Washer fluid, top up": "usability",
    "Garage door opener": "usability", "Interior mirror, garage door opener": "usability",
    "Resting state after door opening": "usability", "Roof function centre": "usability",
    "Towing eye": "usability", "Trailer, use": "usability",
    # keys, access and simple controls are usability, not safety
    "Digital Key": "usability", "Display key": "usability", "Vehicle key": "usability",
    "Vehicle, access and exit": "usability", "Vehicle, lock / unlock": "usability",
    "Automatic doors": "usability", "Horns": "usability", "Flashing": "usability",
    "Interior rearview mirror": "interior", "Interior camera": "interior", "Drive Recorder": "infotainment",
    # customer-facing assistance functions, not homologation topics
    "Cross Traffic Warning Rear with Brake Intervention": "driver_assistance",
    "Emergency Stop Assistant": "driver_assistance", "Fatigue Alert": "driver_assistance",
    "Front collision warning": "driver_assistance", "Rear-end collision warning": "driver_assistance",
    "Night Vision": "driver_assistance", "Rear view camera": "driver_assistance",
}


def slug(s):
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")[:80]


def classify(client, labels):
    """Classify in batches; the model sometimes drops labels, so re-ask for the missing ones."""
    out = {}
    for size in (40, 15, 5):
        todo = [l for l in labels if l not in out]
        out.update(_classify_batches(client, todo, size))
    return out


def _classify_batches(client, labels, size):
    out = {}
    for i in range(0, len(labels), size):
        batch = labels[i:i + size]
        resp = client.chat.completions.create(
            model=CHAT_MODEL, temperature=0, response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": (
                    "Map each BMW customer-feedback category label to exactly one domain key from: "
                    + ", ".join(DOMAINS) + ". Safety equipment, doors, keys, charging hardware, displays and similar vehicle "
                    "features all belong to a domain: pick the closest one. Use 'none' ONLY for labels that are "
                    "clearly not the vehicle itself (owner's manual, general enquiry, customer account/portal, "
                    "dealer or service contact, marketing). "
                    "Reply as JSON: {\"label\": \"domain_key\", ...} with every label given.")},
                {"role": "user", "content": json.dumps(batch, ensure_ascii=False)},
            ],
        )
        out.update({k: v for k, v in json.loads(resp.choices[0].message.content).items() if k in batch})
    return out


def main():
    conn = psycopg.connect(os.environ["SUPABASE_DB_URL"], autocommit=True)
    labels = [r[0] for r in conn.execute(
        "select distinct vfc_level2 from feedback_raw where vfc_level2 is not null order by 1") if r[0] not in SKIP]
    mapping = classify(OpenAI(), labels)
    mapping.update(OVERRIDES)

    def upsert(kind, key, label, parent=None):
        return conn.execute(
            "insert into ontology (kind, key, label, parent_id) values (%s,%s,%s,%s) "
            "on conflict (kind, key) do update set label = excluded.label, parent_id = excluded.parent_id returning id",
            (kind, key, label, parent)).fetchone()[0]

    ids = {k: upsert("domain", k, v) for k, v in DOMAINS.items()}
    for k, v in LINES.items():
        upsert("vehicle_line", k, v)
    for k, v in MARKETS.items():
        upsert("market", k, v)
    mapped, unmapped = 0, []
    for label in labels:
        dom = mapping.get(label)
        if dom in ids:
            upsert("domain", "vfc:" + slug(label), label, ids[dom])
            mapped += 1
        else:
            unmapped.append(label)
    print(f"{len(DOMAINS)} domains, {len(LINES)} vehicle lines, {len(MARKETS)} markets, {mapped} category labels mapped")
    print(f"{len(unmapped)} labels left unmapped: {unmapped}")


if __name__ == "__main__":
    main()
