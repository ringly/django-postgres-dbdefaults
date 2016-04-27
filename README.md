django-postgres-dbdefaults
==========================


A clone of `django.db.backends.postgresql` that supports database defaults. For use with Django 1.9.x.


Motivation - better support database migrations with rolling web server updates
-------------------------------------------------------------------------------

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

For the `django.db.backends.postgresql` module, I have noticed that it actually adds the defaults in the db when it creates columns, but then it removes them in a separate SQL statement. As a result, I have made a subclass of the module that overrides the one string that drops the default and replaces it with a no-op. (This is admittedly a hack, but appears to be the most minimal approach that will survive more updates than copy-pasting large sections of the original class.)

For example `postgresql` might generate SQL for a migration as such:

::

    $ python3 manage.py sqlmigrate app 0010
    BEGIN;
    ALTER TABLE "my_table" ALTER COLUMN "some_column" SET DEFAULT false;
    ALTER TABLE "my_table" ALTER COLUMN "some_column" DROP DEFAULT;
    COMMIT;

With this change, the same migration script turns the 2nd command into a no-op:

::

    $ python3 manage.py sqlmigrate app 0010
    BEGIN;
    ALTER TABLE "my_table" ALTER COLUMN "some_column" SET DEFAULT false;
    ALTER TABLE "my_table" DROP COLUMN IF EXISTS skip_django_drop_default_feature RESTRICT;
    COMMIT;

Furthermore, there's no need to worry about migrations that intend to do `DROP DEFAULT`, because the django migrations code already doesn't do anything in SQL for such a change, it would actually look like this:

::

    $ python3 manage.py sqlmigrate app 0011
    BEGIN;
    --
    -- Alter field some_column on my_table
    --

    COMMIT;


Discussion
----------

I have been using this in production on ringly.com for over a year and safely avoided running into the issues such as a new char field with `null=False` and `default=''` from causing insert errors while some app servers are on new code and others are still on the old code.

I would love to hear ideas that people have about this approach—it seems like it may have been controversial in the past? In my limited use with it, it appears to solve my needs, but I haven’t seen what happens in more complex scenarios such as using a callable for a default (IMO it’s reasonable not to support that specific scenario).

Some discussion on django-developers:

*   [Defaults in the database?](https://groups.google.com/forum/#!searchin/django-developers/database$20defaults/django-developers/aQtt9fKHvjM/H59CaQycDSsJ) - Nov 13, 2006 - 0 replies
*   [defaults in sql (postgres)](https://groups.google.com/forum/#!searchin/django-developers/database$20defaults/django-developers/fHjzttZTkzc/oXbrpBa0dHAJ) - Oct 23, 2007 - 4 replies

Another thought, it maybe adding more flags to migrations that allows deeper customization, but more flags and feature bloat are definitely dangerous things with any framework.

Regardless of what I end up using, I have setup a more rigorous workflow for review migrations before developers push them into our release branch.
