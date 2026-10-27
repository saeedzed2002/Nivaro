"""Idempotent research seed. Existing records/prices/stock are never overwritten."""

import json
from importlib.resources import files
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import HttpUrl
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from nivaro_catalog.domain.contracts import (
    CPU,
    GPU,
    Evidence,
    Localized,
    Offer,
    Peripheral,
    Prebuilt,
    Specifications,
    Variant,
)
from nivaro_catalog.domain.search import normalize_search
from nivaro_catalog.infrastructure.models import CategoryRow, OfferRow, ProductRow, VariantRow
from nivaro_catalog.settings import Settings


def stable_id(key: str) -> UUID:
    return uuid5(NAMESPACE_URL, "https://nivaro.local/seed/" + key)


def search_index(value: str) -> list[str]:
    # Literal token prefixes support a GIN @> query, including Persian terms.
    # Unlike approximate search, this needs neither pg_trgm nor an extra service.
    words = normalize_search(value).split()
    return sorted({word[:length] for word in words for length in range(1, min(len(word), 100) + 1)})


def seed(session: Session) -> None:
    data = json.loads(
        files("nivaro_catalog").joinpath("data/research-products.json").read_text(encoding="utf-8")
    )
    categories = data["categories"] + [
        {"id": "motherboard", "fa": "مادربرد", "en": "Motherboards", "image": "cpu"},
        {"id": "storage", "fa": "ذخیره‌سازی", "en": "Storage", "image": "memory"},
        {"id": "case", "fa": "کیس", "en": "Cases", "image": "showroom"},
        {"id": "psu", "fa": "پاور", "en": "Power supplies", "image": "showroom"},
        {"id": "cooler", "fa": "خنک‌کننده", "en": "Cooling", "image": "showroom"},
    ]
    for category in categories:
        session.execute(
            insert(CategoryRow)
            .values(
                id=stable_id("category/" + category["id"]),
                slug=category["id"],
                name={"fa": category["fa"], "en": category["en"]},
                image=category["image"],
            )
            .on_conflict_do_nothing(index_elements=["id"])
        )
    data["products"].append(
        {
            "slug": "amd-ryzen-7-9700x",
            "name": "AMD Ryzen 7 9700X",
            "category": "cpu",
            "brand": "AMD",
            "image": "cpu",
            "description": {
                "fa": "پردازندهٔ هشت‌هسته‌ای؛ قیمت این بازار هنوز ثبت نشده است.",
                "en": "An eight-core desktop processor; this market has no recorded price yet.",
            },
            "highlights": ["AM5", "8 cores / 16 threads", "DDR5"],
            "offers": {},
        }
    )
    for product in data["products"]:
        product_id = stable_id("product/" + product["slug"])
        category = next(c for c in categories if c["id"] == product["category"])
        cpu_model = "9700X" if product["slug"].endswith("9700x") else "9800X3D"
        specs: Specifications
        if product["category"] == "cpu":
            source = f"https://www.amd.com/en/products/processors/desktops/ryzen/9000-series/amd-ryzen-7-{cpu_model.lower()}.html"
            evidence = [
                Evidence(
                    url=HttpUrl(source),
                    checked_on=data["referenceDate"],
                    note="Official CPU facts; maximum package power and motherboard BIOS support remain unknown",
                )
            ]
            specs = CPU(
                model=f"AMD Ryzen 7 {cpu_model}",
                socket="AM5",
                memory_generation="DDR5",
                max_memory_gb=256,
                cores=8,
                threads=16,
                tdp_w=65 if cpu_model == "9700X" else 120,
                integrated_graphics=True,
                included_cooler=False,
            )
        elif product["category"] == "gpu":
            evidence, specs = [], GPU(vram_gb=12)
        elif product["category"] == "keyboard":
            evidence, specs = [], Peripheral(role="keyboard")
        else:
            evidence, specs = (
                [],
                Prebuilt(
                    cpu_model=product["highlights"][0],
                    gpu_model=product["highlights"][1],
                    memory_gb=32,
                    storage_gb=2000,
                    component_descriptions=product["highlights"],
                ),
            )
        # Tray and boxed CPUs have distinct physical SKU/variant identities.
        packages = (
            ["tray", "boxed"]
            if product["slug"] == "amd-ryzen-7-9800x3d"
            else ["boxed" if product["category"] == "cpu" else "standard"]
        )
        skus = [product["slug"].upper() + "-" + package.upper() for package in packages]
        session.execute(
            insert(ProductRow)
            .values(
                id=product_id,
                slug=product["slug"],
                name=product["name"],
                description=product["description"],
                category_id=stable_id("category/" + product["category"]),
                brand=product["brand"],
                status="published",
                image=product["image"],
                image_ready=True,
                image_kind="illustration",
                highlights=product["highlights"],
                search_tokens=search_index(
                    " ".join(
                        [
                            product["name"],
                            product["brand"],
                            category["fa"],
                            category["en"],
                            *product["description"].values(),
                            *skus,
                        ]
                    )
                ),
            )
            .on_conflict_do_nothing(index_elements=["id"])
        )
        for package, sku in zip(packages, skus, strict=True):
            offers = []
            for market, reference in product["offers"].items():
                if len(packages) > 1 and package != ("tray" if market == "ir" else "boxed"):
                    continue
                offers.append(
                    Offer(
                        market=market,
                        currency=reference["currency"],
                        amount_minor=reference["amountMinor"],
                        seller=reference["seller"],
                        source=Evidence(
                            url=reference["source"],
                            checked_on=data["referenceDate"],
                            note=reference["packaging"]["en"],
                        ),
                    )
                )
            variant = Variant(
                id=stable_id("variant/" + sku),
                sku=sku,
                packaging=Localized(
                    fa={"tray": "تری", "boxed": "باکس", "standard": "نسخهٔ مرجع"}[package],
                    en=package,
                ),
                specifications=specs,
                evidence=evidence,
                stock_kind="stocked_prebuilt"
                if product["category"] == "pc"
                else "accessory"
                if product["category"] == "keyboard"
                else "component",
                offers=offers,
            )
            payload = variant.model_dump(mode="json", exclude={"offers"})
            payload["id"] = variant.id
            session.execute(
                insert(VariantRow)
                .values(**payload, product_id=product_id, version=1)
                .on_conflict_do_nothing(index_elements=["id"])
            )
            for offer in offers:
                session.execute(
                    insert(OfferRow)
                    .values(
                        id=stable_id(f"offer/{sku}/{offer.market}"),
                        variant_id=variant.id,
                        **offer.model_dump(mode="json"),
                    )
                    .on_conflict_do_nothing(index_elements=["id"])
                )


if __name__ == "__main__":
    engine = create_engine(Settings().database_url(), hide_parameters=True)
    with Session(engine) as session, session.begin():
        seed(session)
    print(
        "Catalog research seed applied; existing records preserved. No live stock or sale enabled."
    )
