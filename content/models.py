from django.contrib.auth import get_user_model
from django.db import models
from django.utils.translation import gettext_lazy as _

from aplans.utils import OrderedModel
from aplans.model_images import ModelWithImage


User = get_user_model()


class StaticPage(OrderedModel, ModelWithImage):
    plan = models.ForeignKey(
        'actions.Plan', on_delete=models.CASCADE, related_name='static_pages',
        verbose_name=_('plan')
    )
    parent = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True, related_name='children',
        verbose_name=_('parent page'),
    )
    slug = models.SlugField(max_length=50, verbose_name=_('slug'), blank=True)
    name = models.CharField(max_length=30, verbose_name=_('name'))
    title = models.CharField(max_length=50, verbose_name=_('title'))
    tagline = models.TextField(blank=True, null=True)
    content = models.TextField(blank=True, verbose_name=_('content'))

    is_published = models.BooleanField(default=False, verbose_name=_('is published'))

    modified_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL,
        verbose_name=_('completed by'), editable=False
    )
    created_at = models.DateTimeField(auto_now_add=True, editable=False, verbose_name=_('created at'))
    modified_at = models.DateTimeField(auto_now=True, editable=False, verbose_name=_('modified at'))

    class Meta:
        unique_together = (('plan', 'slug'),)
        verbose_name = _('content page')
        verbose_name_plural = _('content pages')

    def __str__(self):
        return self.title


class BlogPost(ModelWithImage):
    plan = models.ForeignKey(
        'actions.Plan', on_delete=models.CASCADE, related_name='blog_posts',
        verbose_name=_('plan')
    )
    slug = models.CharField(max_length=30, verbose_name=_('slug'))
    title = models.CharField(max_length=40, verbose_name=_('title'))
    content = models.TextField(verbose_name=_('content'))

    is_published = models.BooleanField(default=False, verbose_name=_('is published'))
    published_at = models.DateTimeField(blank=True, null=True, verbose_name=_('published at'))

    modified_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL,
        verbose_name=_('completed by'), editable=False
    )
    created_at = models.DateTimeField(auto_now_add=True, editable=False, verbose_name=_('created at'))
    modified_at = models.DateTimeField(auto_now=True, editable=False, verbose_name=_('modified at'))

    class Meta:
        ordering = ('plan', '-published_at',)
        verbose_name = _('blog post')
        verbose_name_plural = _('blog posts')

    def __str__(self):
        return self.title


class Question(OrderedModel):
    page = models.ForeignKey(
        StaticPage, related_name='questions', on_delete=models.CASCADE,
        verbose_name=_('page'),
    )
    title = models.CharField(verbose_name=_('question title'), max_length=150)
    answer = models.TextField(verbose_name=_('answer'))

    class Meta:
        unique_together = (('page', 'title'),)
        ordering = ('page', 'order',)
        verbose_name = _('question')
        verbose_name_plural = _('questions')

    def __str__(self):
        return self.title
