import random
from django.test import TestCase
from auto_changelog.models import Changelog, ChangelogExample


class ChangelogExampleModelTest(TestCase):
    def setUp(self):
        Changelog.objects.all().delete()

    def tearDown(self):
        Changelog.objects.all().delete()

    def test_new_object_single_changelog(self):
        """ Test we get a single changelog when we create a new object, and that it's mapped to the correct object """
        obj = ChangelogExample.objects.create(name="apples")
        cl = Changelog.objects.all()
        self.assertEqual(1, cl.count())
        self.assertEqual(obj.changelog.all().count(), 1)
        self.assertEqual(cl[0].notes, 'ChangelogExample created')

    def test_lots_of_new_objects(self):
        """ Test that objects get the correct changelogs when added lots at once """
        random.seed(99)
        objects = []

        def addone(site=None, changename=False):
            name = str(random.randint(1000000, 2000000))
            o = ChangelogExample.objects.create(name=name)
            objects.append(name)
            if changename:
                newname = str(random.randint(3000000, 4000000))
                o.name = newname
                o.save()

        for i in range(100):
            addone()

        self.assertEqual(100, Changelog.objects.all().count())

        for i in range(100):
            addone()

        self.assertEqual(200, Changelog.objects.all().count())

        for i in range(100):
            addone(changename=True)

        self.assertEqual(400, Changelog.objects.all().count())

        o = ChangelogExample.objects.get(name=objects[35])
        cl = o.changelog.all()
        self.assertEqual(1, cl.count())
        self.assertEqual(cl[0].notes, 'ChangelogExample created')
