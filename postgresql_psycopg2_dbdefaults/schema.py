import operator

from django.db.models.fields.related import ManyToManyField
from django.utils.six.moves import reduce

from django.db.backends.postgresql_psycopg2.schema import DatabaseSchemaEditor as PGDSE

class DatabaseSchemaEditor(PGDSE):
    """
    This is a direct copy of
    `django.db.backends.postgresql_psycopg2.schema.DatabaseSchemaEditor`,
    but without the calls to `sql_alter_column_no_default` that are used
    to prevent defaults from being in the db--this way our defaults *do*
    go into the db, which makes it easier to migrate the db while old
    code is running.
    """

    def add_field(self, model, field):
        """
        Creates a field on a model.
        Usually involves adding a column, but may involve adding a
        table instead (for M2M fields)
        """
        # Special-case implicit M2M tables
        if isinstance(field, ManyToManyField) and field.rel.through._meta.auto_created:
            return self.create_model(field.rel.through)
        # Get the column's definition
        definition, params = self.column_sql(model, field, include_default=True)
        # It might not actually have a column behind it
        if definition is None:
            return
        # Check constraints can go on the column SQL here
        db_params = field.db_parameters(connection=self.connection)
        if db_params['check']:
            definition += " CHECK (%s)" % db_params['check']
        # Build the SQL and run it
        sql = self.sql_create_column % {
            "table": self.quote_name(model._meta.db_table),
            "column": self.quote_name(field.column),
            "definition": definition,
        }
        self.execute(sql, params)

        # HACK(peter) - don't drop defaults if we specified them!
        # # Drop the default if we need to
        # # (Django usually does not use in-database defaults)
        # if not self.skip_default(field) and field.default is not None:
        #     sql = self.sql_alter_column % {
        #         "table": self.quote_name(model._meta.db_table),
        #         "changes": self.sql_alter_column_no_default % {
        #             "column": self.quote_name(field.column),
        #         }
        #     }
        #     self.execute(sql)

        # Add an index, if required
        if field.db_index and not field.unique:
            self.deferred_sql.append(
                self.sql_create_index % {
                    "name": self._create_index_name(model, [field.column], suffix=""),
                    "table": self.quote_name(model._meta.db_table),
                    "columns": self.quote_name(field.column),
                    "extra": "",
                }
            )
        # Add any FK constraints later
        if field.rel and self.connection.features.supports_foreign_keys and field.db_constraint:
            to_table = field.rel.to._meta.db_table
            to_column = field.rel.to._meta.get_field(field.rel.field_name).column
            self.deferred_sql.append(
                self.sql_create_fk % {
                    "name": self._create_index_name(model, [field.column], suffix="_fk_%s_%s" % (to_table, to_column)),
                    "table": self.quote_name(model._meta.db_table),
                    "column": self.quote_name(field.column),
                    "to_table": self.quote_name(to_table),
                    "to_column": self.quote_name(to_column),
                }
            )
        # Reset connection if required
        if self.connection.features.connection_persists_old_columns:
            self.connection.close()

    def _alter_field(self, model, old_field, new_field, old_type, new_type, old_db_params, new_db_params, strict=False):
        """Actually perform a "physical" (non-ManyToMany) field update."""

        # Has unique been removed?
        if old_field.unique and (not new_field.unique or (not old_field.primary_key and new_field.primary_key)):
            # Find the unique constraint for this field
            constraint_names = self._constraint_names(model, [old_field.column], unique=True)
            if strict and len(constraint_names) != 1:
                raise ValueError("Found wrong number (%s) of unique constraints for %s.%s" % (
                    len(constraint_names),
                    model._meta.db_table,
                    old_field.column,
                ))
            for constraint_name in constraint_names:
                self.execute(
                    self.sql_delete_unique % {
                        "table": self.quote_name(model._meta.db_table),
                        "name": constraint_name,
                    },
                )
        # Drop any FK constraints, we'll remake them later
        fks_dropped = set()
        if old_field.rel and old_field.db_constraint:
            fk_names = self._constraint_names(model, [old_field.column], foreign_key=True)
            if strict and len(fk_names) != 1:
                raise ValueError("Found wrong number (%s) of foreign key constraints for %s.%s" % (
                    len(fk_names),
                    model._meta.db_table,
                    old_field.column,
                ))
            for fk_name in fk_names:
                fks_dropped.add((old_field.column,))
                self.execute(
                    self.sql_delete_fk % {
                        "table": self.quote_name(model._meta.db_table),
                        "name": fk_name,
                    }
                )
        # Drop incoming FK constraints if we're a primary key and things are going
        # to change.
        if old_field.primary_key and new_field.primary_key and old_type != new_type:
            for rel in new_field.model._meta.get_all_related_objects():
                rel_fk_names = self._constraint_names(rel.model, [rel.field.column], foreign_key=True)
                for fk_name in rel_fk_names:
                    self.execute(
                        self.sql_delete_fk % {
                            "table": self.quote_name(rel.model._meta.db_table),
                            "name": fk_name,
                        }
                    )
        # Removed an index?
        if old_field.db_index and not new_field.db_index and not old_field.unique and not (not new_field.unique and old_field.unique):
            # Find the index for this field
            index_names = self._constraint_names(model, [old_field.column], index=True)
            if strict and len(index_names) != 1:
                raise ValueError("Found wrong number (%s) of indexes for %s.%s" % (
                    len(index_names),
                    model._meta.db_table,
                    old_field.column,
                ))
            for index_name in index_names:
                self.execute(
                    self.sql_delete_index % {
                        "table": self.quote_name(model._meta.db_table),
                        "name": index_name,
                    }
                )
        # Change check constraints?
        if old_db_params['check'] != new_db_params['check'] and old_db_params['check']:
            constraint_names = self._constraint_names(model, [old_field.column], check=True)
            if strict and len(constraint_names) != 1:
                raise ValueError("Found wrong number (%s) of check constraints for %s.%s" % (
                    len(constraint_names),
                    model._meta.db_table,
                    old_field.column,
                ))
            for constraint_name in constraint_names:
                self.execute(
                    self.sql_delete_check % {
                        "table": self.quote_name(model._meta.db_table),
                        "name": constraint_name,
                    }
                )
        # Have they renamed the column?
        if old_field.column != new_field.column:
            self.execute(self.sql_rename_column % {
                "table": self.quote_name(model._meta.db_table),
                "old_column": self.quote_name(old_field.column),
                "new_column": self.quote_name(new_field.column),
                "type": new_type,
            })
        # Next, start accumulating actions to do
        actions = []
        post_actions = []
        # Type change?
        if old_type != new_type:
            fragment, other_actions = self._alter_column_type_sql(model._meta.db_table, new_field.column, new_type)
            actions.append(fragment)
            post_actions.extend(other_actions)
        # Default change?
        old_default = self.effective_default(old_field)
        new_default = self.effective_default(new_field)
        if old_default != new_default:
            if new_default is None:
                actions.append((
                    self.sql_alter_column_no_default % {
                        "column": self.quote_name(new_field.column),
                    },
                    [],
                ))
            else:
                if self.connection.features.requires_literal_defaults:
                    # Some databases can't take defaults as a parameter (oracle)
                    # If this is the case, the individual schema backend should
                    # implement prepare_default
                    actions.append((
                        self.sql_alter_column_default % {
                            "column": self.quote_name(new_field.column),
                            "default": self.prepare_default(new_default),
                        },
                        [],
                    ))
                else:
                    actions.append((
                        self.sql_alter_column_default % {
                            "column": self.quote_name(new_field.column),
                            "default": "%s",
                        },
                        [new_default],
                    ))
        # Nullability change?
        if old_field.null != new_field.null:
            if new_field.null:
                actions.append((
                    self.sql_alter_column_null % {
                        "column": self.quote_name(new_field.column),
                        "type": new_type,
                    },
                    [],
                ))
            else:
                actions.append((
                    self.sql_alter_column_not_null % {
                        "column": self.quote_name(new_field.column),
                        "type": new_type,
                    },
                    [],
                ))
        if actions:
            # Combine actions together if we can (e.g. postgres)
            if self.connection.features.supports_combined_alters:
                sql, params = tuple(zip(*actions))
                actions = [(", ".join(sql), reduce(operator.add, params))]
            # Apply those actions
            for sql, params in actions:
                self.execute(
                    self.sql_alter_column % {
                        "table": self.quote_name(model._meta.db_table),
                        "changes": sql,
                    },
                    params,
                )
        if post_actions:
            for sql, params in post_actions:
                self.execute(sql, params)
        # Added a unique?
        if not old_field.unique and new_field.unique:
            self.execute(
                self.sql_create_unique % {
                    "table": self.quote_name(model._meta.db_table),
                    "name": self._create_index_name(model, [new_field.column], suffix="_uniq"),
                    "columns": self.quote_name(new_field.column),
                }
            )
        # Added an index?
        if not old_field.db_index and new_field.db_index and not new_field.unique and not (not old_field.unique and new_field.unique):
            self.execute(
                self.sql_create_index % {
                    "table": self.quote_name(model._meta.db_table),
                    "name": self._create_index_name(model, [new_field.column], suffix="_uniq"),
                    "columns": self.quote_name(new_field.column),
                    "extra": "",
                }
            )
        # Type alteration on primary key? Then we need to alter the column
        # referring to us.
        rels_to_update = []
        if old_field.primary_key and new_field.primary_key and old_type != new_type:
            rels_to_update.extend(new_field.model._meta.get_all_related_objects())
        # Changed to become primary key?
        # Note that we don't detect unsetting of a PK, as we assume another field
        # will always come along and replace it.
        if not old_field.primary_key and new_field.primary_key:
            # First, drop the old PK
            constraint_names = self._constraint_names(model, primary_key=True)
            if strict and len(constraint_names) != 1:
                raise ValueError("Found wrong number (%s) of PK constraints for %s" % (
                    len(constraint_names),
                    model._meta.db_table,
                ))
            for constraint_name in constraint_names:
                self.execute(
                    self.sql_delete_pk % {
                        "table": self.quote_name(model._meta.db_table),
                        "name": constraint_name,
                    },
                )
            # Make the new one
            self.execute(
                self.sql_create_pk % {
                    "table": self.quote_name(model._meta.db_table),
                    "name": self._create_index_name(model, [new_field.column], suffix="_pk"),
                    "columns": self.quote_name(new_field.column),
                }
            )
            # Update all referencing columns
            rels_to_update.extend(new_field.model._meta.get_all_related_objects())
        # Handle our type alters on the other end of rels from the PK stuff above
        for rel in rels_to_update:
            rel_db_params = rel.field.db_parameters(connection=self.connection)
            rel_type = rel_db_params['type']
            self.execute(
                self.sql_alter_column % {
                    "table": self.quote_name(rel.model._meta.db_table),
                    "changes": self.sql_alter_column_type % {
                        "column": self.quote_name(rel.field.column),
                        "type": rel_type,
                    }
                }
            )
        # Does it have a foreign key?
        if new_field.rel and \
           (fks_dropped or (old_field.rel and not old_field.db_constraint)) and \
           new_field.db_constraint:
            to_table = new_field.rel.to._meta.db_table
            to_column = new_field.rel.get_related_field().column
            self.execute(
                self.sql_create_fk % {
                    "table": self.quote_name(model._meta.db_table),
                    "name": self._create_index_name(model, [new_field.column], suffix="_fk_%s_%s" % (to_table, to_column)),
                    "column": self.quote_name(new_field.column),
                    "to_table": self.quote_name(to_table),
                    "to_column": self.quote_name(to_column),
                }
            )
        # Rebuild FKs that pointed to us if we previously had to drop them
        if old_field.primary_key and new_field.primary_key and old_type != new_type:
            for rel in new_field.model._meta.get_all_related_objects():
                self.execute(
                    self.sql_create_fk % {
                        "table": self.quote_name(rel.model._meta.db_table),
                        "name": self._create_index_name(rel.model, [rel.field.column], suffix="_fk"),
                        "column": self.quote_name(rel.field.column),
                        "to_table": self.quote_name(model._meta.db_table),
                        "to_column": self.quote_name(new_field.column),
                    }
                )
        # Does it have check constraints we need to add?
        if old_db_params['check'] != new_db_params['check'] and new_db_params['check']:
            self.execute(
                self.sql_create_check % {
                    "table": self.quote_name(model._meta.db_table),
                    "name": self._create_index_name(model, [new_field.column], suffix="_check"),
                    "column": self.quote_name(new_field.column),
                    "check": new_db_params['check'],
                }
            )

        # HACK(peter) - don't drop defaults if we specified them!
        # # Drop the default if we need to
        # # (Django usually does not use in-database defaults)
        # if not self.skip_default(new_field) and new_field.default is not None:
        #     sql = self.sql_alter_column % {
        #         "table": self.quote_name(model._meta.db_table),
        #         "changes": self.sql_alter_column_no_default % {
        #             "column": self.quote_name(new_field.column),
        #         }
        #     }
        #     self.execute(sql)

        # Reset connection if required
        if self.connection.features.connection_persists_old_columns:
            self.connection.close()
