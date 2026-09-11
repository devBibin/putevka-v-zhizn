import re
from html import unescape
from urllib.parse import parse_qs, urlsplit

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Course, School, Subject


class CoursePaginationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="course-reader")
        cls.school = School.objects.create(name="Школа 12")
        cls.subject = Subject.objects.create(name="Математика", slug="math")

    def setUp(self):
        self.client.force_login(self.user)
        self.url = reverse("study:schools")

    def make_courses(self, count):
        Course.objects.bulk_create([
            Course(school=self.school, subject=self.subject,
                   title=f"Курс {i:02d}", description="ЕГЭ 12 & + page=2")
            for i in range(count)
        ])

    def links(self, response):
        return [unescape(link) for link in re.findall(
            r'class="page-link" href="([^"]+)"', response.content.decode()
        )]

    def test_first_page_at_pagination_boundary(self):
        for count in (0, 12, 13, 25):
            with self.subTest(count=count):
                Course.objects.all().delete()
                self.make_courses(count)
                response = self.client.get(self.url)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(len(response.context["courses"]), min(count, 12))
                self.assertEqual(self.links(response), ["?page=2"] if count > 12 else [])

    def test_navigation_preserves_filters(self):
        self.make_courses(25)
        filters = {"school": str(self.school.pk), "subject": str(self.subject.pk),
                   "q": "ЕГЭ 12 & + page=2"}
        response = self.client.get(self.url, {**filters, "page": "2"})
        links = self.links(response)
        self.assertEqual(len(links), 2)
        for link, page, count in zip(links, ("1", "3"), (12, 1)):
            self.assertEqual(parse_qs(urlsplit(link).query),
                             {**{key: [value] for key, value in filters.items()}, "page": [page]})
            target = self.client.get(self.url + link)
            self.assertEqual(target.status_code, 200)
            self.assertEqual(target.context["courses"].number, int(page))
            self.assertEqual(len(target.context["courses"]), count)

    def test_invalid_page_uses_paginator_fallback(self):
        self.make_courses(25)
        for value, expected in (("", 1), ("abc", 1), ("999", 3), ("0", 3), ("-1", 3)):
            with self.subTest(page=value):
                response = self.client.get(self.url, {"page": value})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.context["courses"].number, expected)
