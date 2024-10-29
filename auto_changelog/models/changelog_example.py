from django.db import models, transaction
from auto_changelog.models import ChangelogModelMixin, Changelog


class ChangelogExample(models.Model, ChangelogModelMixin):
    changelog = models.ManyToManyField(Changelog)
    name = models.CharField(unique=True, max_length=255)

    @transaction.atomic
    def save(self, **kwargs):
        self.save_with_changelog(super().save, kwargs)
