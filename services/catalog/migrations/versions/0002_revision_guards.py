"""Reject unversioned technical/price changes and malformed specification kinds."""

from alembic import op

revision = "0002_revision_guards"
down_revision = "0001_catalog"
branch_labels = None
depends_on = None


def upgrade():
    op.create_check_constraint(
        "spec_kind_known",
        "variants",
        "jsonb_typeof(specifications->'kind') = 'string' AND specifications->>'kind' IN ('cpu','motherboard','memory','storage','case','psu','cooler','gpu','peripheral','prebuilt')",
    )
    op.execute("""
      CREATE FUNCTION guard_variant_revision() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN
        IF NEW.spec_version < OLD.spec_version OR
           ((NEW.specifications IS DISTINCT FROM OLD.specifications OR NEW.evidence IS DISTINCT FROM OLD.evidence)
             AND NEW.spec_version <= OLD.spec_version)
        THEN RAISE EXCEPTION 'Technical changes require a newer specification revision' USING ERRCODE = '23514';
        END IF;
        NEW.updated_at = now();
        RETURN NEW;
      END $$;
      CREATE TRIGGER variant_revision BEFORE UPDATE ON variants
      FOR EACH ROW EXECUTE FUNCTION guard_variant_revision();
      CREATE FUNCTION guard_offer_revision() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN
        IF NEW.price_version < OLD.price_version OR
           ((NEW.amount_minor IS DISTINCT FROM OLD.amount_minor OR NEW.currency IS DISTINCT FROM OLD.currency
             OR NEW.market IS DISTINCT FROM OLD.market OR NEW.available_for_sale IS DISTINCT FROM OLD.available_for_sale
             OR NEW.reference_only IS DISTINCT FROM OLD.reference_only)
             AND NEW.price_version <= OLD.price_version)
        THEN RAISE EXCEPTION 'Offer changes require a newer price revision' USING ERRCODE = '23514';
        END IF;
        NEW.updated_at = now();
        RETURN NEW;
      END $$;
      CREATE TRIGGER offer_revision BEFORE UPDATE ON market_offers
      FOR EACH ROW EXECUTE FUNCTION guard_offer_revision();
    """)
    op.execute("""
      CREATE OR REPLACE FUNCTION check_category_depth() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN
        PERFORM pg_advisory_xact_lock(1768846913, 1);
        IF NEW.parent_id IS NOT NULL THEN
          IF NEW.parent_id = NEW.id
             OR EXISTS (SELECT 1 FROM categories WHERE id = NEW.parent_id AND parent_id IS NOT NULL)
             OR EXISTS (SELECT 1 FROM categories WHERE parent_id = NEW.id)
          THEN RAISE EXCEPTION 'Category depth exceeds two levels' USING ERRCODE = '23514';
          END IF;
        END IF;
        RETURN NEW;
      END $$;
    """)


def downgrade():
    raise RuntimeError(
        "Forward-only guard migration; data-preserving rollback requires a reviewed new migration"
    )
