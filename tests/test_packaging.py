# -*- coding: utf-8 -*-
"""Готовность к публикации: plugin.json, запись магазина и workflow.

Проверки дешёвые, но ловят ровно те ошибки, из-за которых PR в
Flow-Launcher/Flow.Launcher.PluginsManifest отклоняют или собранный релиз не
устанавливается: расхождение версии между plugin.json и записью магазина, чужой
ID, битая ссылка на архив, отсутствие workflow автосборки, разошедшиеся имена
иконки и архива.
"""

import glob
import json
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STORE_DIR = os.path.join(ROOT, "store")
WORKFLOW_DIR = os.path.join(ROOT, ".github", "workflows")

# Обязательные поля plugin.json по документации Flow Launcher.
REQUIRED_MANIFEST_KEYS = ("ID", "ActionKeyword", "Name", "Description", "Author",
                          "Version", "Language", "Website", "IcoPath",
                          "ExecuteFileName")

VERSION_RE = re.compile(r"\A\d+\.\d+\.\d+\Z")
UUID_RE = re.compile(r"\A[0-9A-Fa-f]{8}(-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12}\Z")


def read_json(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def read_text(path):
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


class TestPluginJson(unittest.TestCase):
    def setUp(self):
        self.plugin = read_json(os.path.join(ROOT, "plugin.json"))

    def test_has_every_required_key(self):
        for key in REQUIRED_MANIFEST_KEYS:
            self.assertTrue(self.plugin.get(key), "plugin.json: пустое поле %s" % key)

    def test_id_is_a_uuid(self):
        self.assertRegex(self.plugin["ID"], UUID_RE)

    def test_version_is_semver(self):
        self.assertRegex(self.plugin["Version"], VERSION_RE)

    def test_language_and_entry_point(self):
        self.assertEqual(self.plugin["Language"], "python")
        self.assertTrue(self.plugin["ExecuteFileName"].endswith(".py"))
        self.assertTrue(os.path.exists(os.path.join(ROOT, self.plugin["ExecuteFileName"])))

    def test_icon_exists(self):
        icon = self.plugin["IcoPath"].replace("\\", "/")
        self.assertTrue(os.path.exists(os.path.join(ROOT, icon)), icon)

    def test_website_is_the_project_url(self):
        self.assertEqual(self.plugin["Website"],
                         "https://github.com/RADiant-Git/Flow-AHK-Launcher")

    def test_action_keyword_is_lowercase_without_spaces(self):
        self.assertRegex(self.plugin["ActionKeyword"], r"\A[a-z0-9]+\Z")


class TestStoreEntry(unittest.TestCase):
    """Файл, который копируется в plugins/ репозитория манифеста."""

    def setUp(self):
        self.plugin = read_json(os.path.join(ROOT, "plugin.json"))
        found = glob.glob(os.path.join(STORE_DIR, "*.json"))
        self.assertEqual(len(found), 1, "ожидалась ровно одна запись магазина")
        self.path = found[0]
        self.entry = read_json(self.path)

    def test_file_name_follows_the_convention(self):
        # <Name>-<uuid>.json, где uuid — 36 символов с дефисами внутри.
        base = os.path.basename(self.path)[:-len(".json")]
        uuid, name = base[-36:], base[:-37]
        self.assertEqual(uuid, self.plugin["ID"])
        self.assertTrue(name, "имя файла должно быть <Name>-<uuid>.json")
        self.assertFalse(name.endswith("-"), name)

    def test_copied_fields_match_plugin_json(self):
        for key in ("ID", "Name", "Description", "Author", "Version", "Language",
                    "Website"):
            self.assertEqual(self.entry[key], self.plugin[key],
                             "поле %s разошлось с plugin.json" % key)

    def test_download_url_points_at_this_version(self):
        url = self.entry["UrlDownload"]
        self.assertIn("/releases/download/v%s/" % self.plugin["Version"], url)
        self.assertTrue(url.startswith(self.plugin["Website"] + "/"), url)

    def test_source_url_is_the_project(self):
        self.assertEqual(self.entry["UrlSourceCode"], self.plugin["Website"])

    def test_icon_matches_plugin_json_and_is_a_cdn_url(self):
        icon = self.plugin["IcoPath"].replace("\\", "/")
        self.assertTrue(self.entry["IcoPath"].startswith("https://cdn.jsdelivr.net/gh/"))
        self.assertTrue(self.entry["IcoPath"].endswith("/" + icon),
                        "IcoPath записи магазина разошёлся с plugin.json")


class TestReleaseWorkflow(unittest.TestCase):
    def setUp(self):
        self.entry = read_json(glob.glob(os.path.join(STORE_DIR, "*.json"))[0])
        self.text = read_text(os.path.join(WORKFLOW_DIR, "publish-release.yml"))

    def test_archive_name_matches_the_store_entry(self):
        self.assertIn(os.path.basename(self.entry["UrlDownload"]), self.text)

    def test_version_comes_from_plugin_json(self):
        self.assertIn("plugin.json", self.text)
        self.assertIn("GITHUB_OUTPUT", self.text)
        self.assertIn("tag_name", self.text)

    def test_tests_run_before_publishing(self):
        self.assertIn("needs: test", self.text)

    def test_zip_layout_is_verified(self):
        self.assertIn("Verify zip layout", self.text)
        self.assertIn("zipfile.ZipFile", self.text)

    def test_ci_workflow_exists(self):
        self.assertTrue(os.path.exists(os.path.join(WORKFLOW_DIR, "ci.yml")))


class TestRepositoryLayout(unittest.TestCase):
    def test_both_readmes_exist(self):
        for name in ("README.md", "README.ru.md"):
            self.assertTrue(os.path.exists(os.path.join(ROOT, name)), name)

    def test_readmes_point_at_each_other(self):
        english = read_text(os.path.join(ROOT, "README.md"))
        russian = read_text(os.path.join(ROOT, "README.ru.md"))
        self.assertIn("(README.ru.md)", english)
        self.assertIn("(README.md)", russian)

    def test_no_stale_documents_are_referenced(self):
        """README не должен ссылаться на удалённые файлы."""
        for name in ("README.md", "README.ru.md"):
            text = read_text(os.path.join(ROOT, name))
            for stale in ("README.en.md", "CHANGELOG.md", "CONTRIBUTING.md",
                          "packaging/"):
                self.assertNotIn(stale, text, "%s ссылается на %s" % (name, stale))

    def test_user_data_is_not_tracked_by_git(self):
        ignore = read_text(os.path.join(ROOT, ".gitignore"))
        for entry in ("/modules.json", "/session.json", "/runtime.ahk"):
            self.assertIn(entry, ignore, ".gitignore: нет %s" % entry)


if __name__ == "__main__":
    unittest.main()
