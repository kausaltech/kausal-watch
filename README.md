# aplans

aplans is a service for administrating and monitoring action plans. It has the following components:

- admin UI for modifying action plan content
- REST API for distributing the information

The service was first used to implement monitoring for the [Carbon-neutral Helsinki 2035 action plan](https://www.stadinilmasto.fi/files/2018/03/Executive_summary_HNH2035.pdf). The [ReactJS UI code](https://github.com/City-of-Helsinki/cnh-ui) is also open source.

## Installation

### Development

Install the required Python packages:

```shell
pip install -r requirements.txt
```

Create a file called `.env` in your repo root with the following contents:

```
DEBUG=1
DATABASE_URL=postgis:///aplans
```

Make sure you have created a Postgres database with the same name (here `aplans`).

Run migrations:

```shell
python manage.py migrate
```

Create a superuser:
> You might need the following translations during the createsuperuser operation: käyttäjätunnus = username, sähköpostiosoite = e-mail

```shell
python manage.py createsuperuser
```

Compile the translation files:

```shell
python manage.py compilemessages
```

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
