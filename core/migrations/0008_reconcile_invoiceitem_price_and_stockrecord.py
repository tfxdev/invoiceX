# Reconciles the *database* schema with the model state that migration 0005
# already declared.
#
# Background: 0002 was hand-edited to drop the invoice_type/price additions,
# and 0003/0004 were replaced with empty stubs while 0005 declared
# invoice_type / invoiceitem.price / StockRecord as *state-only*
# (SeparateDatabaseAndState with no database operations). That assumption only
# holds for the one database that happened to be migrated before the files were
# gutted. On any freshly created database those three objects never get built,
# and the app dies with:
#
#     OperationalError: no such column: core_invoiceitem.price
#
# This migration is idempotent: it inspects the live schema and only creates
# what is actually missing, so it is a no-op on the already-correct database.
# It carries no state operations because the model state is already correct.

from django.db import migrations

STOCKRECORD_DDL = (
    'CREATE TABLE "core_stockrecord" ('
    '"id" integer NOT NULL PRIMARY KEY AUTOINCREMENT, '
    '"qty" integer NOT NULL, '
    '"note" text NULL, '
    '"stock_type" varchar(20) NOT NULL, '
    '"date" datetime NOT NULL, '
    '"product_id" bigint NOT NULL REFERENCES "core_product" ("id") '
    'DEFERRABLE INITIALLY DEFERRED, '
    '"user_id" integer NULL REFERENCES "auth_user" ("id") '
    'DEFERRABLE INITIALLY DEFERRED)'
)

STOCKRECORD_INDEXES = [
    'CREATE INDEX "core_stockrecord_product_id_ea7fec26" '
    'ON "core_stockrecord" ("product_id")',
    'CREATE INDEX "core_stockrecord_user_id_22ba2910" '
    'ON "core_stockrecord" ("user_id")',
]


def _columns(cursor, introspection, table):
    return {c.name for c in introspection.get_table_description(cursor, table)}


def forwards(apps, schema_editor):
    connection = schema_editor.connection
    introspection = connection.introspection
    with connection.cursor() as cursor:
        tables = set(introspection.table_names(cursor))

        if "core_invoiceitem" in tables:
            if "price" not in _columns(cursor, introspection, "core_invoiceitem"):
                cursor.execute(
                    'ALTER TABLE "core_invoiceitem" ADD COLUMN "price" decimal NULL'
                )

        if "core_invoice" in tables:
            if "invoice_type" not in _columns(cursor, introspection, "core_invoice"):
                cursor.execute(
                    'ALTER TABLE "core_invoice" ADD COLUMN '
                    '"invoice_type" varchar(20) NULL'
                )

        if "core_stockrecord" not in tables:
            cursor.execute(STOCKRECORD_DDL)
            for stmt in STOCKRECORD_INDEXES:
                cursor.execute(stmt)


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0007_alter_invoice_discount_value"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[],
            database_operations=[
                migrations.RunPython(forwards, migrations.RunPython.noop),
            ],
        ),
    ]
