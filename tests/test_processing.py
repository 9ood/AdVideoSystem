import os
import tempfile
import unittest
from unittest.mock import patch

import app as app_module
from ai_analyzer import AIAnalyzer, AIServiceError


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
        self.ok = 200 <= status_code < 300
        self.text = str(payload)

    def json(self):
        return self._payload


class InvalidJsonResponse:
    def __init__(self, text="not-json"):
        self.status_code = 200
        self.ok = True
        self.text = text

    def json(self):
        raise ValueError("invalid json")


class TimeoutThenSuccess:
    def __init__(self):
        self.calls = 0

    def __call__(self, *args, **kwargs):
        self.calls += 1
        if self.calls == 1:
            raise __import__("requests").Timeout("timed out")
        return FakeResponse(
            200,
            {
                "choices": [{"message": {"content": "ok after timeout retry"}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            },
        )


class FakeVideoProcessor:
    def __init__(self, video_path, output_dir):
        self.video_path = video_path
        self.output_dir = output_dir

    def detect_scenes(self):
        return [(0, 1)]

    def extract_keyframes(self, scenes):
        frame_path = os.path.join(self.output_dir, "scene_001_keyframe.jpg")
        with open(frame_path, "wb") as handle:
            handle.write(b"fake")
        return [
            {
                "scene_number": 1,
                "start_time": 0.0,
                "end_time": 1.0,
                "duration": 1.0,
                "keyframe_path": frame_path,
                "first_frame_path": frame_path,
                "last_frame_path": frame_path,
            }
        ]


class FailingAnalyzer:
    def __init__(self, api_key, model, base_url=None):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url

    def analyze_frame(self, image_path):
        raise AIServiceError("分析镜头画面失败：模型不可用")


class ProcessFlowTests(unittest.TestCase):
    def test_ai_analyzer_falls_back_to_available_model(self):
        forbidden = FakeResponse(
            403,
            {"error": {"message": "This model is not available in your region.", "code": 403}},
        )
        success = FakeResponse(
            200,
            {
                "choices": [{"message": {"content": "ok from fallback"}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            },
        )

        with patch.dict(
            os.environ,
            {"AI_FALLBACK_MODELS": "qwen/qwen2.5-vl-72b-instruct"},
            clear=False,
        ):
            analyzer = AIAnalyzer("test-key", "google/gemini-3-flash-preview")
            with patch.object(analyzer, "encode_image", return_value="abc"), patch(
                "ai_analyzer.requests.post",
                side_effect=[forbidden, success],
            ), patch("ai_analyzer._log_token_usage"):
                result = analyzer.analyze_frame("unused.jpg")

        self.assertEqual(result, "ok from fallback")
        self.assertEqual(analyzer.model, "qwen/qwen2.5-vl-72b-instruct")

    def test_process_video_returns_error_when_ai_service_fails(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            upload_dir = os.path.join(temp_dir, "uploads")
            output_dir = os.path.join(temp_dir, "outputs")
            os.makedirs(upload_dir, exist_ok=True)
            os.makedirs(output_dir, exist_ok=True)

            video_path = os.path.join(upload_dir, "task_demo.mp4")
            with open(video_path, "wb") as handle:
                handle.write(b"fake video")

            app_module.app.config["TESTING"] = True
            app_module.app.config["UPLOAD_FOLDER"] = upload_dir
            app_module.app.config["OUTPUT_FOLDER"] = output_dir

            with app_module.app.test_client() as client, patch.object(
                app_module,
                "get_task_video",
                return_value=("demo.mp4", video_path),
            ), patch.object(
                app_module,
                "VideoProcessor",
                FakeVideoProcessor,
            ), patch.object(
                app_module,
                "AIAnalyzer",
                FailingAnalyzer,
            ), patch.dict(
                os.environ,
                {"OPENROUTER_API_KEY": "test-key"},
                clear=False,
            ):
                response = client.post("/process/task-demo")

        self.assertEqual(response.status_code, 502)
        data = response.get_json()
        self.assertIn("模型不可用", data["error"])

    def test_ai_analyzer_retries_when_provider_returns_invalid_json(self):
        bad = InvalidJsonResponse(" \n \n provider glitch")
        success = FakeResponse(
            200,
            {
                "choices": [{"message": {"content": "ok after retry"}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            },
        )

        analyzer = AIAnalyzer("test-key", "qwen/qwen3.6-plus")
        with patch.object(analyzer, "encode_image", return_value="abc"), patch(
            "ai_analyzer.requests.post",
            side_effect=[bad, success],
        ), patch("ai_analyzer._log_token_usage"):
            result = analyzer.analyze_frame("unused.jpg")

        self.assertEqual(result, "ok after retry")
        self.assertEqual(analyzer.model, "qwen/qwen3.6-plus")

    def test_qwen_openrouter_requests_disable_reasoning_by_default(self):
        analyzer = AIAnalyzer(
            "test-key",
            "qwen/qwen3.6-plus",
            base_url="https://openrouter.ai/api/v1/chat/completions",
        )

        payload = analyzer._build_request_payload(
            "qwen/qwen3.6-plus",
            [{"role": "user", "content": "hello"}],
        )

        self.assertEqual(payload["reasoning"]["effort"], "none")
        self.assertTrue(payload["reasoning"]["exclude"])

    def test_non_qwen_models_do_not_force_reasoning_config(self):
        analyzer = AIAnalyzer(
            "test-key",
            "google/gemini-3-flash-preview",
            base_url="https://openrouter.ai/api/v1/chat/completions",
        )

        payload = analyzer._build_request_payload(
            "google/gemini-3-flash-preview",
            [{"role": "user", "content": "hello"}],
        )

        self.assertNotIn("reasoning", payload)

    def test_generate_script_messages_do_not_repeat_image_input(self):
        analyzer = AIAnalyzer("test-key", "gemini-3.1-flash-lite-preview")

        messages = analyzer._build_generate_script_messages("A person speaks to camera.")

        self.assertEqual(messages[0]["content"][0]["type"], "text")
        self.assertEqual(len(messages[0]["content"]), 1)

    def test_ai_analyzer_retries_after_timeout(self):
        retry_post = TimeoutThenSuccess()
        analyzer = AIAnalyzer("test-key", "gemini-3.1-flash-lite-preview")

        with patch(
            "ai_analyzer.requests.post",
            side_effect=retry_post,
        ), patch("ai_analyzer._log_token_usage"), patch("ai_analyzer.time.sleep"):
            result = analyzer.generate_script("unused.jpg", "A person speaks to camera.")

        self.assertEqual(result, "ok after timeout retry")
        self.assertEqual(retry_post.calls, 2)

    def test_generate_script_normalizes_single_line_output(self):
        analyzer = AIAnalyzer("test-key", "gemini-3.1-flash-lite-preview")

        with patch.object(
            analyzer,
            "_request_chat_completion",
            return_value="台词：今天这款产品真的很适合刚开始学琴的小朋友。",
        ):
            result = analyzer.generate_script("unused.jpg", "A person speaks to camera.")

        self.assertEqual(result, "今天这款产品真的很适合刚开始学琴的小朋友。")

    def test_generate_script_returns_empty_for_no_dialogue(self):
        analyzer = AIAnalyzer("test-key", "gemini-3.1-flash-lite-preview")

        with patch.object(
            analyzer,
            "_request_chat_completion",
            return_value="无台词",
        ):
            result = analyzer.generate_script("unused.jpg", "No one is speaking.")

        self.assertEqual(result, "")


if __name__ == "__main__":
    unittest.main()
