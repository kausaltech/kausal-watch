# aplans

aplans is a service for administrating and monitoring action plans. It has the following components:

- admin UI for modifying action plan content
- REST API for distributing the information

The service was first used to implement monitoring for the [Carbon-neutral Helsinki 2035 action plan](https://www.stadinilmasto.fi/files/2018/03/Executive_summary_HNH2035.pdf). The [ReactJS UI code](https://github.com/City-of-Helsinki/cnh-ui) is also open source.

## Installation

### Development

#### Installation

Install the required Python packages:

```shell
pip install -r requirements.txt
```

> _Notes for macOS users:_
>
> - _The optional rustface package hasn't been built for latest macOS versions and breaks installation. Comment out all references to rustface in the requirements._
> - _Install these additional dependencies with homebrew:_ `brew install libvoikko gdal postgis`

#### Setup

Create a `.env` file in your repo root with the following contents. Ask a teammate for the values of `AZURE_AD_` variables.

```
DEBUG=1
DATABASE_URL=postgis:///aplans
AZURE_AD_CLIENT_ID=
AZURE_AD_CLIENT_SECRET=
```

Build the Kausal extensions:

1. Clone the [kausal-extensions](https://github.com/kausaltech/kausal-extensions) repo
2. Follow the [kausal-extensions instructions](https://github.com/kausaltech/kausal-extensions#building) to build the client
3. Create a symlink in the root of kausal-watch-private
   ```shell
   ln -s ../kausal-extensions/watch/kausal_watch_extensions .
   ```

Collect static files:

```shell
python manage.py collectstatic
```

Make sure you have created a Postgres database with the same name (here `aplans`).

Run migrations:

```shell
python manage.py migrate
```

Create a superuser:

> _Note: You might need the following translations during the createsuperuser operation: käyttäjätunnus = username, sähköpostiosoite = e-mail_

```shell
python manage.py createsuperuser
```

To access the admin UI with the created superuser, create and associate a `Person` with it:

```shell
python manage.py shell_plus
```
```python
superuser = User.objects.get(email="<email of the superuser you created>")
organization = Organization.objects.get(abbreviation='Kausal')  # Found only if database is prepopulated with the help of a coworker

person = Person.objects.create(
    user=superuser,
    first_name="<first name of your user>",
    last_name="<last name of your user>",
    email="<email of the superuser you created>",
    organization=organization
)
person.save()
```

Compile the translation files:

```shell
python manage.py compilemessages
```

Run the development server, the Admin UI will be available at [localhost:8000](http://localhost:8000):

```shell
python manage.py runserver
```

> _Note: the database will be empty, ask a teammate for help to restore your local database from a backup_

### Production

The project is containerized using Docker Compose. You will still need to set some
variables in your environment; see the first few lines in `aplans/settings.py`.

In particular, you will need to set the database credentials; for example:

```
POSTGRES_PASSWORD=change_me
DATABASE_URL=postgis://watch:change_me@db/watch
```

## Contributing

### Python requirements

This project uses two files for requirements. The workflow is as follows.

`requirements.txt` is not edited manually, but is generated
with `pip-compile`.

`requirements.txt` always contains fully tested, pinned versions
of the requirements. `requirements.in` contains the primary, unpinned
requirements of the project without their dependencies.

In production, deployments should always use `requirements.txt`
and the versions pinned therein. In development, new virtualenvs
and development environments should also be initialised using
`requirements.txt`. `pip-sync` will synchronize the active
virtualenv to match exactly the packages in `requirements.txt`.

In development and testing, to update to the latest versions
of requirements, use the command `pip-compile`. You can
use [requires.io](https://requires.io) to monitor the
pinned versions for updates.

To remove a dependency, remove it from `requirements.in`,
run `pip-compile` and then `pip-sync`. If everything works
as expected, commit the changes.

### Updating translations

To extract translatable strings and update translations in the `locale` directory, run the following command (example for the `de` locale):

```
python manage.py makemessages --locale de --add-location=file --no-wrap --keep-pot
```

The option `--keep-pot` retains the `.pot` files that can be used as the source files for external translation services.

However, this does not update the translatable strings for the notification templates, which have the extension `.mjml`. To do this, run the following:

```
pybabel extract -F babel.cfg --input-dirs=. -o locale/notifications.pot --add-location=file --no-wrap
```

We use `pybabel` instead of `makemessages` because notification templates use Jinja2 and not the Django template language.

To create a new message catalog (`.po` file) from the generated `.pot` file, you can run the following (example for the `de` locale):

```
pybabel init -D notifications -i locale/notifications.pot -d locale -l de
```

For subsequently updating this catalog, run the following:

```
pybabel update -D notifications -i locale/notifications.pot -d locale -l de
```

The equivalent of `compilemessages` for the MJML templates is the following (example for the `de` locale):

```
pybabel compile -D notifications -d locale -l de
```
