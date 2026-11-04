import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from trafik.ajan import calistir


class AgentBudget(unittest.TestCase):
    def test_parallel_tool_calls_cannot_exceed_step_budget_and_usage_is_saved(self):
        calls = [SimpleNamespace(type="function_call", name="intersection_summary", arguments="{}", call_id=str(i),
                  model_dump=lambda **_: {"type": "function_call", "name": "intersection_summary", "arguments": "{}"}) for i in range(3)]
        usage = SimpleNamespace(model_dump=lambda **_: {"input_tokens": 10, "output_tokens": 2,
                                                       "input_tokens_details": {"cached_tokens": 0}})
        responses = [SimpleNamespace(output=calls, output_text="", usage=usage),
                     SimpleNamespace(output=[], output_text='{"recommended_plan":{}}', usage=usage)]
        client = SimpleNamespace(responses=SimpleNamespace(create=Mock(side_effect=responses)))
        environment = SimpleNamespace(intersection_summary=Mock(return_value={"ok": True}))
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"MODEL_API_KEY": "test-placeholder"}), \
                patch("trafik.ajan.OpenAI", return_value=client), patch("trafik.ajan.Ortam", return_value=environment), \
                patch("trafik.ajan.dogrula", return_value={"local": True}):
            result = calistir(en_cok_adim=2, kayit_klasoru=folder)
            self.assertTrue(Path(result["yol"]).is_file())
        self.assertEqual(environment.intersection_summary.call_count, 2)
        self.assertEqual(len(result["adimlar"]), 2)
        self.assertEqual(len(result["api_kullanim"]), 2)
        self.assertEqual(result["maliyet"]["input_tokens"], 20)
        self.assertEqual(result["maliyet"]["output_tokens"], 4)
        self.assertTrue(all(c.kwargs["max_output_tokens"] == 8192 for c in client.responses.create.call_args_list))
        self.assertNotIn("tool_choice", client.responses.create.call_args_list[-1].kwargs)
        self.assertNotIn("tools", client.responses.create.call_args_list[-1].kwargs)

    def test_api_failure_preserves_usage_and_completed_tool_steps(self):
        call = SimpleNamespace(type="function_call", name="intersection_summary", arguments="{}", call_id="1",
                               model_dump=lambda **_: {"type": "function_call", "name": "intersection_summary", "arguments": "{}"})
        usage = SimpleNamespace(model_dump=lambda **_: {"input_tokens": 10, "output_tokens": 2})
        client = SimpleNamespace(responses=SimpleNamespace(create=Mock(side_effect=[
            SimpleNamespace(output=[call], output_text="", usage=usage), RuntimeError("API unavailable")
        ])))
        environment = SimpleNamespace(intersection_summary=Mock(return_value={"ok": True}))
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"MODEL_API_KEY": "test-placeholder"}), \
                patch("trafik.ajan.OpenAI", return_value=client), patch("trafik.ajan.Ortam", return_value=environment):
            with self.assertRaises(RuntimeError):
                calistir(en_cok_adim=2, kayit_klasoru=folder)
            import json
            saved = json.loads(next(Path(folder).glob("kosu_*.json")).read_text(encoding="utf-8"))
            self.assertEqual(saved["durum"], "api_hatasi")
            self.assertEqual(len(saved["adimlar"]), 1)
            self.assertEqual(len(saved["api_kullanim"]), 1)

    def test_truncated_json_is_not_marked_complete(self):
        usage = SimpleNamespace(model_dump=lambda **_: {"input_tokens": 10, "output_tokens": 8192})
        client = SimpleNamespace(responses=SimpleNamespace(create=Mock(return_value=
            SimpleNamespace(output=[], output_text='{"recommended_plan":', usage=usage))))
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"MODEL_API_KEY": "test-placeholder"}), \
                patch("trafik.ajan.OpenAI", return_value=client), patch("trafik.ajan.Ortam"), \
                patch("trafik.ajan.dogrula", return_value={"gecerli_json": False}):
            result = calistir(en_cok_adim=2, kayit_klasoru=folder)
        self.assertIsNone(result["cevap"])
        self.assertEqual(result["durum"], "cevap_gecersiz")

    def test_incomplete_plan_preserves_final_response_when_verification_fails(self):
        text = '{"recommended_plan":{"sol_onde":14}}'
        usage = SimpleNamespace(model_dump=lambda **_: {"input_tokens": 10, "output_tokens": 2})
        client = SimpleNamespace(responses=SimpleNamespace(create=Mock(return_value=
            SimpleNamespace(output=[], output_text=text, usage=usage))))
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"MODEL_API_KEY": "test-placeholder"}), \
                patch("trafik.ajan.OpenAI", return_value=client), patch("trafik.ajan.Ortam"):
            with self.assertRaises(KeyError):
                calistir(kayit_klasoru=folder)
            saved = json.loads(next(Path(folder).glob("kosu_*.json")).read_text(encoding="utf-8"))
        self.assertEqual(saved["durum"], "dogrulama_hatasi")
        self.assertEqual(saved["hata_turu"], "KeyError")
        self.assertEqual(saved["cevap_metni"], text)
        self.assertEqual(saved["cevap"], json.loads(text))
        self.assertEqual(saved["maliyet"]["input_tokens"], 10)
        self.assertEqual(len(saved["api_kullanim"]), 1)

    def test_final_response_is_on_disk_before_a_failing_notification(self):
        text = '{"recommended_plan":{}}'
        usage = SimpleNamespace(model_dump=lambda **_: {"input_tokens": 10, "output_tokens": 2})
        client = SimpleNamespace(responses=SimpleNamespace(create=Mock(return_value=
            SimpleNamespace(output=[], output_text=text, usage=usage))))
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"MODEL_API_KEY": "test-placeholder"}), \
                patch("trafik.ajan.OpenAI", return_value=client), patch("trafik.ajan.Ortam"), \
                patch("trafik.ajan.dogrula") as verify:
            def fail_notification(event):
                saved = json.loads(next(Path(folder).glob("kosu_*.json")).read_text(encoding="utf-8"))
                self.assertEqual(saved["cevap_metni"], text)
                self.assertEqual(saved["maliyet"]["output_tokens"], 2)
                raise RuntimeError("UI disconnected")

            with self.assertRaises(RuntimeError):
                calistir(kayit_klasoru=folder, bildir=fail_notification)
            saved = json.loads(next(Path(folder).glob("kosu_*.json")).read_text(encoding="utf-8"))
            verify.assert_not_called()
        self.assertEqual(saved["durum"], "bildirim_hatasi")
        self.assertEqual(saved["hata_turu"], "RuntimeError")
        self.assertEqual(saved["cevap_metni"], text)


if __name__ == "__main__":
    unittest.main()
