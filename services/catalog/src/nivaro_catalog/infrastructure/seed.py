"""Load sourced retail references and optional inventory for local simulator use."""

import argparse
import json
from importlib.resources import files
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import HttpUrl, TypeAdapter
from sqlalchemy import create_engine, update
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
from nivaro_catalog.domain.search import search_index
from nivaro_catalog.infrastructure.models import CategoryRow, OfferRow, ProductRow, VariantRow
from nivaro_catalog.settings import Settings


def stable_id(key: str) -> UUID:
    return uuid5(NAMESPACE_URL, "https://nivaro.local/seed/" + key)


def seed(session: Session, *, demo_stock: bool = False) -> None:
    resources = files("nivaro_catalog").joinpath("data")
    data = json.loads(resources.joinpath("research-products.json").read_text(encoding="utf-8"))
    retail = json.loads(resources.joinpath("retail-offers.json").read_text(encoding="utf-8"))
    retired = (
        "razer-blackwidow-v4-75",
        "kingston-fury-beast-rgb-kf560c36bbeak2-32",
        "corsair-4000d-airflow-cc-9011200-ww",
        "seasonic-focus-gx-850-atx-31",
        "noctua-nh-u12s",
    )
    session.execute(
        update(ProductRow)
        .where(
            ProductRow.id.in_([stable_id("product/" + slug) for slug in retired]),
            ProductRow.version == 1,
            ProductRow.status == "published",
        )
        .values(status="archived", version=ProductRow.version + 1)
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
                "fa": "پردازندهٔ هشت‌هسته‌ای دسکتاپ برای پلتفرم AM5.",
                "en": "An eight-core desktop processor for the AM5 platform.",
            },
            "highlights": ["AM5", "8 cores / 16 threads", "DDR5"],
        }
    )
    data["products"].extend(
        json.loads(
            files("nivaro_catalog")
            .joinpath("data/builder-components.json")
            .read_text(encoding="utf-8")
        )
    )
    for product in data["products"]:
        product_id = stable_id("product/" + product["slug"])
        category = next(c for c in categories if c["id"] == product["category"])
        cpu_model = "9700X" if product["slug"].endswith("9700x") else "9800X3D"
        specs: Specifications
        if "specifications" in product:
            specs = TypeAdapter(Specifications).validate_python(product["specifications"])
            evidence = [Evidence.model_validate(item) for item in product["evidence"]]
        elif product["category"] == "cpu":
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
        packages = ["tray", "boxed"] if product["category"] == "cpu" else ["standard"]
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
        legacy_description = {
            "amd-ryzen-7-9700x": "An eight-core desktop processor; this market has no recorded price yet.",
            "samsung-990-pro-1tb-mz-v9p1t0bw": "1 TB NVMe drive, model without heatsink. No market price is recorded.",
        }.get(product["slug"])
        if legacy_description is not None:
            session.execute(
                update(ProductRow)
                .where(
                    ProductRow.id == product_id,
                    ProductRow.version == 1,
                    ProductRow.description["en"].astext == legacy_description,
                )
                .values(description=product["description"], version=ProductRow.version + 1)
            )
        for package, sku in zip(packages, skus, strict=True):
            offers = []
            for market, reference in retail["offers"][product["slug"]].items():
                if len(packages) > 1 and package != ("tray" if market == "ir" else "boxed"):
                    continue
                amount, seller, source, note = reference
                offers.append(
                    Offer(
                        market=market,
                        currency="IRR" if market == "ir" else "USD",
                        amount_minor=amount,
                        seller=seller,
                        source=Evidence(
                            url=source,
                            checked_on=retail["checkedOn"],
                            note=note,
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
            if demo_stock:
                session.execute(
                    update(VariantRow)
                    .where(
                        VariantRow.id == variant.id,
                        VariantRow.version == 1,
                        VariantRow.on_hand == 0,
                        VariantRow.stock_verified.is_(False),
                    )
                    .values(on_hand=20, stock_verified=True, version=VariantRow.version + 1)
                )
            for offer in offers:
                values = offer.model_dump(mode="json")
                offer_id = stable_id(f"offer/{sku}/{offer.market}")
                if demo_stock:
                    values.update(available_for_sale=True, reference_only=False)
                original_reference = OfferRow.source == values["source"]
                initial_reference = OfferRow.source["checked_on"].astext == data["referenceDate"]
                session.execute(
                    insert(OfferRow)
                    .values(id=offer_id, variant_id=variant.id, **values)
                    .on_conflict_do_update(
                        constraint="uq_variant_market",
                        set_=values | {"price_version": OfferRow.price_version + 1},
                        where=(OfferRow.id == offer_id)
                        & (OfferRow.price_version == 1)
                        & OfferRow.reference_only.is_(True)
                        & (
                            initial_reference | original_reference
                            if demo_stock
                            else initial_reference
                        ),
                    )
                )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo-stock", action="store_true")
    args = parser.parse_args()
    engine = create_engine(Settings().database_url(), hide_parameters=True)
    with Session(engine) as session, session.begin():
        seed(session, demo_stock=args.demo_stock)
    print(
        "Retail references loaded. Simulator inventory enabled."
        if args.demo_stock
        else "Retail references loaded."
    )
