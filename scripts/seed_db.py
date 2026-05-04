from __future__ import annotations

from pathlib import Path

import yaml
from sqlalchemy import select

from app.config import ROOT_DIR
from app.db.models import Benchmark, Commodity, Company, CompanyCommodityExposure
from app.db.session import get_session


def load_yaml(name: str):
    with (ROOT_DIR / "app" / "seeds" / name).open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def upsert_by(session, model, key_name: str, values: dict):
    item = session.scalar(select(model).where(getattr(model, key_name) == values[key_name]))
    if item is None:
        item = model(**values)
        session.add(item)
    else:
        for key, value in values.items():
            setattr(item, key, value)
    session.flush()
    return item


def main() -> None:
    session = get_session()
    commodities = {}
    try:
        for row in load_yaml("commodities.yml")["commodities"]:
            commodity = upsert_by(session, Commodity, "code", row)
            commodities[commodity.code] = commodity

        for row in load_yaml("benchmarks.yml")["benchmarks"]:
            upsert_by(session, Benchmark, "market", row)

        for row in load_yaml("companies.yml")["companies"]:
            exposures = row.pop("exposures")
            company = upsert_by(session, Company, "ticker", row)
            for exposure in exposures:
                commodity = commodities[exposure["commodity_code"]]
                existing = session.scalar(
                    select(CompanyCommodityExposure).where(
                        CompanyCommodityExposure.company_id == company.id,
                        CompanyCommodityExposure.commodity_id == commodity.id,
                    )
                )
                values = {
                    "company_id": company.id,
                    "commodity_id": commodity.id,
                    "exposure_type": exposure["exposure_type"],
                    "exposure_direction": exposure["exposure_direction"],
                    "exposure_score": exposure["exposure_score"],
                    "notes": exposure.get("notes", ""),
                }
                if existing is None:
                    session.add(CompanyCommodityExposure(**values))
                else:
                    for key, value in values.items():
                        setattr(existing, key, value)
        session.commit()
        print("Seed data loaded.")
    finally:
        session.close()


if __name__ == "__main__":
    main()

