django-postgres-dbdefaults
==========================

A clone of `django.db.backends.postgresql_psycopg2` with database defaults. For use with Django 1.7.

Motivation
----------

The Django migrations (new in Django 1.7) do not insert default values into the database. I would like database defaults to allow me to update the database with new migrations while it is still running an older version of a web app. For example, the majority of my updates follow this general pattern:

1.  remove one machine from my production load balancer
2.  run the latest database migrations for the database used by all production web servers
3.  update the code on my machine that is out of the load balancer and verify things work directly on that server
4.  udpate the remaining web servers with the latest code

This creates a delay between the database update and the newest code, which could lead to failed database inserts during that period if a column is not null and its default is not set in the database.

Some people suggest creating an additional data migration script to add the defaults by hand, which would help solve the problem, but (a) this is easy to miss and (b) I’m guessing this would create a brief window of time where the column exists without a default and could still lead to a failed insert.

Furthermore, some of the [existing documentation](https://docs.djangoproject.com/en/1.7/topics/migrations/#postgresql) is vague and doesn’t make it clear that database defaults are not included in migrations.

Solution
--------

For the `django.db.backends.postgresql_psycopg2` module, I have noticed that it actually adds the defaults in the db when it creates columns, but then it removes them in a separate SQL statement. As a result, I have made sort of a subclass of the module that makes the bare minimum changes to remove the logic where the schema editor drops these defaults (unless a change in the models actually does call for a default to be dropped).

For example `postgresql_psycopg2` might generate SQL for a migration as such:

::

    $ python3 manage.py sqlmigrate app 0010
    BEGIN;
    ALTER TABLE "my_table" ALTER COLUMN "some_column" SET DEFAULT false;
    ALTER TABLE "my_table" ALTER COLUMN "some_column" DROP DEFAULT;
    COMMIT;

With this change, the same migration script would just look like this:

::

    $ python3 manage.py sqlmigrate app 0010
    BEGIN;
    ALTER TABLE "my_table" ALTER COLUMN "some_column" SET DEFAULT false;
    COMMIT;

Discussion
----------

I would love to hear ideas that people have about this approach—it seems like it may have been contreversial in the past? In my limited use with it, it appears to solve my needs, but I haven’t seen what happens in more complex scenarios such as using a callable for a default (IMO it’s reasonable not to support that specific scenario).

Some discussion on django-developers:

*   [Defaults in the database?](https://groups.google.com/forum/#!searchin/django-developers/database$20defaults/django-developers/aQtt9fKHvjM/H59CaQycDSsJ) - Nov 13, 2006 - 0 replies
*   [defaults in sql (postgres)](https://groups.google.com/forum/#!searchin/django-developers/database$20defaults/django-developers/fHjzttZTkzc/oXbrpBa0dHAJ) - Oct 23, 2007 - 4 replies

Another thought, it maybe adding more flags to migrations that allows deeper customization, but more flags and feature bloat are definitely dangerous things with any framework.

Regardless of what I end up using, I have setup a more rigorous workflow for review migrations before developers push them into our release branch.
