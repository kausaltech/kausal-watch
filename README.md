# Kausal Watch

Kausal Watch is a service for administrating and monitoring action plans. It has the following components:

- admin UI for modifying action plan content
- REST API for distributing the information

The service was first used to implement monitoring for the [Carbon-neutral Helsinki 2035 action plan](https://www.stadinilmasto.fi/files/2018/03/Executive_summary_HNH2035.pdf). The [ReactJS UI code](https://github.com/City-of-Helsinki/cnh-ui) is also open source.

## Installation

### Run in Docker locally

Build the Docker containers first with:

```shell
docker compose build
```

Then start them with:

```shell
docker compose -f docker-compose.yml -f docker-compose.local.yml up -d app
```

This should start an HTTP server on `localhost`, port `8000`. To be able to log in,
you'll need to create a user together with some test data:

```shell
docker compose exec app ./manage.py create_superuser_with_defaults \
  --email superuser@example.com --organization "Test org" \
  --first-name Super --last-name User
```

After the command above finishes, you can point your browser at [localhost:8000](http://localhost:8000)
and log in using the password you provided.

### Development

#### Installation

In the project root directory, create and activate a Python virtual environment:

```shell
uv venv
source .venv/bin/activate
```

Install the required Python packages:

```shell
uv sync
```

If you have access to the Kausal private extensions, check out the optional submodule.
A plain `git submodule update --init` skips it on purpose, so it needs an explicit `--checkout`:

```shell
git submodule update --init --checkout private/extensions
```

The `kausal_watch_extensions` package then becomes importable through the committed
`src/kausal_watch_extensions` symlink. When the submodule is absent, the symlink dangles and
the extension is simply not installed.

#### Setup

Create a `.env` file in your repo root with the following contents. Ask a teammate for the values of `AZURE_AD_` variables.

```
DEBUG=1
DATABASE_URL=postgis:///aplans
AZURE_AD_CLIENT_ID=
AZURE_AD_CLIENT_SECRET=
```

Build the Kausal extensions (only relevant when the submodule is checked out):

```shell
mise deps
```

This installs the extension client's Node dependencies, builds its bundles into the extension's
`static/` directory, and compiles its translations. The provider configuration lives in the
submodule (`private/extensions/mise/watch.toml`) and is loaded through `mise/conf.d/`. Whenever a
submodule update changes the client sources or translation files, `mise` reminds you to rerun it
and `mise run` does so automatically.

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
superuser = User.objects.get(email='<email of the superuser you created>')
organization = Organization.objects.get(
    abbreviation='Kausal'
)  # Found only if database is prepopulated with the help of a coworker

person = Person.objects.create(
    user=superuser,
    first_name='<first name of your user>',
    last_name='<last name of your user>',
    email='<email of the superuser you created>',
    organization=organization,
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

We use `uv` to manage dependencies. Invoke `uv sync -P <PACKAGE>` to upgrade one package,
and `uv sync -U` to upgrade all of them.


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
