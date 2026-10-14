import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

import api as api_mod


def sample_result(answer: str = "The fee is 120,000.", standalone: str = "What is the BS SE fee?"):
    return {
        "answer": answer,
        "standalone": standalone,
        "hits": [
            {
                "section_path": ["Fees", "BS Software Engineering"],
                "page_start": 47,
                "page_end": 47,
                "score": 0.91234,
                "text": "Tuition fee is 120,000 per semester.",
            }
        ],
    }


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.mock_retriever = MagicMock()
        self.mock_retriever.chunks = [{"id": i} for i in range(4)]
        self.retriever_patch = patch.object(api_mod, "Retriever", return_value=self.mock_retriever)
        self.answer_patch = patch.object(api_mod, "answer", return_value=sample_result())
        self.retriever_patch.start()
        self.mock_answer = self.answer_patch.start()
        api_mod._sessions.clear()
        self._client_cm = TestClient(api_mod.app)
        self.client = self._client_cm.__enter__()

    def tearDown(self):
        self._client_cm.__exit__(None, None, None)
        self.answer_patch.stop()
        self.retriever_patch.stop()
        api_mod._sessions.clear()

    def test_health_ready(self):
        res = self.client.get("/health")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["chunks_loaded"], 4)

    def test_health_not_ready(self):
        api_mod.retriever = None
        res = self.client.get("/health")
        self.assertEqual(res.status_code, 503)

    def test_empty_question_rejected(self):
        res = self.client.post("/chat", json={"question": "   "})
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["detail"], "Question cannot be empty.")

    def test_chat_response_shape(self):
        res = self.client.post(
            "/chat",
            json={"question": "What is the fee?", "session_id": None, "rewrite": False, "k": 8},
        )
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertIn("session_id", body)
        self.assertEqual(body["answer"], "The fee is 120,000.")
        self.assertEqual(body["standalone_question"], "What is the BS SE fee?")
        self.assertEqual(body["sources"][0]["page_start"], 47)
        self.assertEqual(body["sources"][0]["score"], 0.9123)

    def test_session_continuity(self):
        first = self.client.post("/chat", json={"question": "What is the fee?"}).json()
        sid = first["session_id"]
        self.client.post("/chat", json={"question": "and for hosts?", "session_id": sid})
        self.assertEqual(self.mock_answer.call_count, 2)
        second_kwargs = self.mock_answer.call_args.kwargs
        self.assertEqual(second_kwargs["history"], [("What is the fee?", "The fee is 120,000.")])
        self.assertEqual(second_kwargs["q"], "and for hosts?")

    def test_clear_session(self):
        sid = self.client.post("/chat", json={"question": "fees?"}).json()["session_id"]
        res = self.client.delete(f"/chat/{sid}")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), {"cleared": sid})
        self.assertNotIn(sid, api_mod._sessions)


if __name__ == "__main__":
    unittest.main()
