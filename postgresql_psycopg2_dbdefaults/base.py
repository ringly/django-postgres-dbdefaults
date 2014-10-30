
from django.db.backends.postgresql_psycopg2.base import *
from django.db.backends.postgresql_psycopg2.base import DatabaseWrapper as PGDBW

from .schema import DatabaseSchemaEditor

class DatabaseWrapper(PGDBW):
    """
    Exactly the same as `django.db.backends.postgresql_psycopg2.base.DatabaseWrapper`
    except it uses a different `schema_editor` such that database migrations
    put defaults into the database (instead of dropping them).
    """
    def schema_editor(self, *args, **kwargs):
        "Returns a new instance of this backend's SchemaEditor"
        return DatabaseSchemaEditor(self, *args, **kwargs)
