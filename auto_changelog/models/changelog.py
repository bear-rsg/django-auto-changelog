import logging
from django.db import models
from django.forms import model_to_dict
from django.db.models.signals import m2m_changed
from threading import Lock
from auto_changelog.middleware import get_current_username


logger = logging.getLogger(__name__)


class Changelog(models.Model):
    """
    Changelog
    """
    notes = models.TextField()
    reference = models.TextField(null=True)
    calling_user = models.TextField(null=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp', ]
        indexes = [models.Index(fields=['reference']), ]

    def __str__(self):
        return f"<Changelog {self.id}: {self.notes} {self.reference} {self.calling_user} {self.timestamp}"

    def referrer(self):
        """
        Use our m2m field reverse calls to find the referring object as human-readable string
        """
        possib = []
        for name in dir(self):
            if name.endswith('_set') and not name.startswith('_'):
                fn = getattr(self, name)
                possib.extend(fn.all())

        if len(possib) == 1:
            return f'{possib[0].__class__.__name__}: {possib[0]}'
        else:
            return f"ERROR: Couldn't find related object for changelog id {self.id}"


def human(model, pk):
    """
    Return the human-readable name for this entry, if possible
    """
    try:
        instance = model.objects.get(pk=pk)
    except model.DoesNotExist:
        # This kind of thing can happen in bootstrapping and installing fixtures
        return str(pk)

    name = getattr(instance, 'name', None)
    if name and getattr(model, 'name').field.unique:
        # There is a unique name field - use that
        return name
    for field in model._meta.fields:
        if field.unique and 'name' in field.name:
            # Best guess field to use
            return getattr(instance, field.name)

    # Last chance option
    return str(pk)


_m2m_lock = Lock()  # m2m hooks get called asynchronously
_last_m2m_change = {}


def m2m_changed_hook(*, sender, instance, action, pk_set, model, **kwargs):
    """
    Automatical changelog writing for ManyToManyFields
    """
    assert model != Changelog  # avoid infinite loop!

    if action not in ('post_add', 'post_remove'):
        return

    if pk_set == {None}:
        return

    if not hasattr(instance, 'new_changelog'):
        # Doesn't support changelogs
        return

    logger.debug("m2m_changed_hook: %s %s %s %s %s", instance, action, pk_set, model, sender)

    with _m2m_lock:
        my_change = (instance.id, action, pk_set)
        # The hook gets called once per item - so de-duplicate like this
        if _last_m2m_change.get(action) == my_change:
            return

        _last_m2m_change[action] = my_change

        items = ', '.join(human(model, pk) for pk in pk_set)
        if action == 'post_add':
            action_text = 'Added'
        elif action == 'post_remove':
            action_text = 'Removed'
        else:
            return

        notes = f"{action_text} {model._meta.model_name} ({sender._meta.model_name}) {items}"
        instance.new_changelog(notes)


def find_changes(obj):
    """
    Find any changes for this object when compared with what's stored in the database

    @param obj: A django model instance

    Returns a list of strings describing the changes to the object.
    """
    db_obj = obj.__class__.objects.get(id=obj.id)
    db_data = model_to_dict(db_obj)
    my_data = model_to_dict(obj)

    changes = {}
    for key, value in my_data.items():
        db_value = db_data.get(key)
        if db_value != value:
            field = getattr(obj.__class__, key).field
            if isinstance(field, models.ForeignKey):
                db_value = human(field.related_model, db_value)
                value = human(field.related_model, value)
            changes[key] = f"{db_value} -> {value}"

    notes = []
    for key in sorted(changes):
        notes.append(f"Changed {key}: {changes[key]}")

    return notes


class ChangelogModelMixin(object):
    def __init__(self):
        if self.id is not None:
            # We can only register for a m2m hook when we already exist in the database
            self._register()

    def _register(self):
        """
        Register our hooks for the ManyToManyFields for this model
        """
        for field in self._meta.many_to_many:
            if field.related_model != Changelog:
                through = getattr(self, field.name).through
                uid = self.__class__.__name__  # make sure we only register once per class
                m2m_changed.connect(m2m_changed_hook, sender=through, dispatch_uid=uid)

    def save_with_changelog(self, save, save_kwargs):
        """
        Get the current object from the database, and compare it with what we've got now. Then create a new changelog
        entry for the differences. This involves an extra database query, but is simple and therefore preferable to
        a more complex solution that doesn't.

        This is designed to be called from a model's save method, which should be protected in by @transaction.atomic.

        @param save: the save method to call (usually super().save)
        @param save_kwargs: the kwargs to pass to the save method
        """
        if not hasattr(self.__class__, 'changelog'):
            raise AttributeError("Model %s does not have a changelog field", self.__class__.__name__)

        if self.id is None:
            # We have to save the object (for the first time) before adding a changelog
            save(**save_kwargs)
            self.new_changelog(f"{self.__class__.__name__} created")
            # Register this object for any future m2m changes
            self._register()
            return

        notes = find_changes(self)
        if notes:
            # Only add the changelog if there's something to say
            self.new_changelog('\n'.join(notes))

        # Finally save the object
        save(**save_kwargs)

    def new_changelog(self, notes, reference='auto'):
        """
        Log a new changelog with the supplied notes
        """
        user = get_current_username()
        self.changelog.create(reference=reference, notes=notes, calling_user=user)
        logger.info("Added changelog '%s' to %s", notes, self)
