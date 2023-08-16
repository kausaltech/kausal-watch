import json
from django.core.management.base import BaseCommand
from django.db import transaction
from wagtail.models import PageLogEntry

from content.models import StaticPage as OldStaticPage
from pages.models import PlanRootPage
from pages.models import StaticPage as NewStaticPage


def set_subtree(root, parent=None):
    root.set_url_path(parent)
    root.save(update_fields=['url_path'])
    for child in root.get_children():
        set_subtree(child, root)


def migrate_page(old_page):
    # Get questions and answers
    questions = [{
        'question': question.title,
        'answer': question.answer,
    } for question in old_page.questions.all()]
    qa_section_block = {
        'heading': 'Usein kysytyt kysymykset',
        'questions': questions,
    }

    # Map old to new field names
    # FIXME: We ignore the `image` field for now.
    field_mapping = {
        'slug': 'slug',
        'name': 'seo_title',
        'title': 'title',
        'tagline': 'lead_paragraph',
        'top_menu': 'show_in_menus',
        'footer': 'show_in_footer',
        'is_published': 'live',
        'modified_by': 'owner',
        'created_at': 'first_published_at',
        'modified_at': 'last_published_at',
    }
    data = {new_field: getattr(old_page, old_field) for old_field, new_field in field_mapping.items()}
    data.update({
        'has_unpublished_changes': not old_page.is_published,
        'body': json.dumps([
            {'type': 'paragraph', 'value': old_page.content},
            {'type': 'qa_section', 'value': qa_section_block},
        ]),
    })
    new_page = NewStaticPage(**data)
    plan_root = old_page.plan.root_page
    plan_root.add_child(instance=new_page)

    # On saving, Wagtail created a page log entry with timestamp being now. This needs to be fixed manually.
    page_log_entry = PageLogEntry.objects.get(page=new_page)
    page_log_entry.timestamp = data['first_published_at']
    page_log_entry.save()

    old_page.was_migrated = True
    old_page.save()


class Command(BaseCommand):
    help = "Migrate legacy static pages from the `content` app to the `pages` app"

    @transaction.atomic
    def handle(self, *args, **options):
        # Fix plan root page url_paths
        for node in PlanRootPage.objects.all():
            set_subtree(node)

        for page in OldStaticPage.objects.filter(was_migrated=False):
            migrate_page(page)
