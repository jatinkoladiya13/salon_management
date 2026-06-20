from django.core.management.base import BaseCommand
from django.db import connection
from django.db.utils import ProgrammingError


class Command(BaseCommand):
    help = 'Create and copy schema in PostgreSQL'

    def add_arguments(self, parser):
        # Adding an argument to the command
        parser.add_argument('new_schema_name', type=str, help='The name of the new schema to create')

    def handle(self, *args, **kwargs):
        new_schema_name = kwargs['new_schema_name']
        old_schema_name = 'template_schema'  # Existing schema name
        self.create_and_copy_schema(old_schema_name, new_schema_name)

    def create_and_copy_schema(self, old_schema_name, new_schema_name):
        create_schema_sql = f"CREATE SCHEMA {new_schema_name};"

        copy_tables_sql = f"""
        DO $$
        DECLARE
            table_record RECORD;
        BEGIN
            FOR table_record IN
                SELECT tablename
                FROM pg_tables
                WHERE schemaname = '{old_schema_name}'
            LOOP
                EXECUTE format('CREATE TABLE {new_schema_name}.%I (LIKE {old_schema_name}.%I INCLUDING ALL);', table_record.tablename, table_record.tablename);
            END LOOP;
        END $$;
        """

        copy_data_sql = f"""
        DO $$
        DECLARE
            table_record RECORD;
        BEGIN
            FOR table_record IN
                SELECT tablename
                FROM pg_tables
                WHERE schemaname = '{old_schema_name}'
            LOOP
                EXECUTE format('INSERT INTO {new_schema_name}.%I SELECT * FROM {old_schema_name}.%I;', table_record.tablename, table_record.tablename);
            END LOOP;
        END $$;
        """

        with connection.cursor() as cursor:
            try:
                # Step 1: Create the new schema
                self.stdout.write(self.style.NOTICE(f"Creating schema '{new_schema_name}'"))
                cursor.execute(create_schema_sql)

                # Step 2: Copy tables
                self.stdout.write(self.style.NOTICE(f"Copying tables from '{old_schema_name}' to '{new_schema_name}'"))
                cursor.execute(copy_tables_sql)

                # Step 3: Copy data
                self.stdout.write(self.style.NOTICE(f"Copying data from '{old_schema_name}' to '{new_schema_name}'"))
                cursor.execute(copy_data_sql)
            except ProgrammingError as e:
                self.stderr.write(self.style.ERROR(f"Error executing SQL: {e}"))
            else:
                self.stdout.write(self.style.SUCCESS(f"Schema '{new_schema_name}' created and populated successfully from '{old_schema_name}'"))
