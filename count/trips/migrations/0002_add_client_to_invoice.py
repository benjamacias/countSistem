from django.db import migrations


def add_client_field(apps, schema_editor):
    table = 'trips_invoice'
    column = 'client_id'
    with schema_editor.connection.cursor() as cursor:
        columns = [col.name for col in schema_editor.connection.introspection.get_table_description(cursor, table)]
        if column not in columns:
            cursor.execute(
                'ALTER TABLE %s ADD COLUMN %s BIGINT REFERENCES trips_client(id)' % (table, column)
            )


class Migration(migrations.Migration):

    dependencies = [
        ("trips", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(add_client_field, migrations.RunPython.noop),
    ]
