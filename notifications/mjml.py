import logging
import os
import subprocess

from django.conf import settings
from django.utils import translation
from django.utils.formats import date_format
from jinja2 import FileSystemLoader, StrictUndefined
from jinja2.sandbox import SandboxedEnvironment
from sentry_sdk import capture_exception

logger = logging.getLogger(__name__)


MJML_CMD = [
    os.path.join(settings.BASE_DIR, 'node_modules', '.bin', 'mjml'),
    '-c', 'ignoreIncludes=true',
    '--config.validationLevel', 'strict',
    '-i', '-s',
]


def format_date(dt):
    current_language = translation.get_language()
    if current_language == 'fi':
        dt_format = r'j.n.Y'
    else:
        # default to English
        dt_format = r'j/n/Y'

    return date_format(dt, dt_format)


def make_jinja_environment():
    loader = FileSystemLoader(os.path.join(settings.BASE_DIR, 'notifications', 'mjml-templates'))
    env = SandboxedEnvironment(
        trim_blocks=True, lstrip_blocks=True, undefined=StrictUndefined, loader=loader,
        extensions=[
            'jinja2.ext.i18n'
        ]
    )
    env.filters['format_date'] = format_date
    return env


def render_mjml(mjml_in, dump=None):
    try:
        p = subprocess.run(
            MJML_CMD, input=mjml_in, capture_output=True, encoding='utf8', check=True,
        )
    except subprocess.CalledProcessError as e:
        logger.error(e.stderr)
        capture_exception(e)

    if dump:
        for idx, line in enumerate(mjml_in.splitlines()):
            print('%d. %s' % (idx, line))
        with open('%s.mjml' % dump, 'w', encoding='utf8') as f:
            f.write(mjml_in)
        with open('%s.html' % dump, 'w', encoding='utf8') as f:
            f.write(p.stdout)

    if p.stderr:
        logger.warning('Warnings from MJML:\n%s' % p.stderr)

    return p.stdout


def render_mjml_from_template(template_name, context, dump=None):
    env = make_jinja_environment()
    template = env.get_template('%s.mjml' % template_name)
    return render_mjml(template.render(context), dump=dump)
