from django.db.backends.postgresql.schema import DatabaseSchemaEditor as DjangoDatabaseSchemaEditor


class DatabaseSchemaEditor(DjangoDatabaseSchemaEditor):

    # HACK - this field is used only in calls to drop a default value via:
    #
    #     ALTER COLUMN %(column)s DROP NOT NULL
    #
    # Which gets passed in as "changes" to:
    #
    #     sql_alter_column = "ALTER TABLE %(table)s %(changes)s"
    #
    # So what we're doing here is creating a no-op that fits within the existing
    # django contructs without touching too much code.
    #
    sql_alter_column_no_default = "DROP COLUMN IF EXISTS skip_django_drop_default_feature RESTRICT"
