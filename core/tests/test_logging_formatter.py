import json
import logging

from django.test import SimpleTestCase

from core.logging import StructuredJSONFormatter


class StructuredJSONFormatterTests(SimpleTestCase):
    def test_format_returns_valid_json_with_special_characters_in_message(self):
        formatter = StructuredJSONFormatter(datefmt="%Y-%m-%dT%H:%M:%S%z")
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname=__file__,
            lineno=10,
            msg='mensagem com "aspas" e quebra\nlinha',
            args=(),
            exc_info=None,
        )

        rendered = formatter.format(record)
        payload = json.loads(rendered)

        self.assertEqual(payload["logger"], "test.logger")
        self.assertEqual(payload["level"], "INFO")
        self.assertEqual(payload["message"], 'mensagem com "aspas" e quebra\nlinha')
        self.assertIn("timestamp", payload)

    def test_format_includes_extra_context_fields(self):
        formatter = StructuredJSONFormatter()
        record = logging.LogRecord(
            name="test.logger.extra",
            level=logging.WARNING,
            pathname=__file__,
            lineno=32,
            msg="evento com contexto",
            args=(),
            exc_info=None,
        )
        record.employee_id = 123
        record.phone_line_id = 456
        record.actor_id = 789

        rendered = formatter.format(record)
        payload = json.loads(rendered)

        self.assertEqual(payload["employee_id"], 123)
        self.assertEqual(payload["phone_line_id"], 456)
        self.assertEqual(payload["actor_id"], 789)
