"""Unit tests cho SocialTrendingService (hệ thống cào và xử lý Real-Time Social Trends)."""
import json
import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from app.services.trending.models import SocialTrendDigest, SocialTrendItem
from app.services.trending.service import SocialTrendingService

SAMPLE_DDG_HTML = b"""<!DOCTYPE html>
<html>
<body>
<table>
<tr><td><a href="https://thegioididong.com/hoi-dap/tong-hop-tu-vung-cau-noi-trend-tiktok-1587842">Tong hop cau noi trend TikTok</a></td></tr>
<tr><td class="result-snippet">C\xc3\xa1c c\xc3\xa2u n\xc3\xb3i viral nh\xc6\xb0 "H\xe1\xbb\x93i chi\xe1\xbb\x81u tr\xe1\xbb\x9di m\xc6\xb0a", "To6", "S\xc3\xadt r\xe1\xbb\x8bt" g\xc3\xa2y b\xc3\xa3o m\xe1\xba\xa1ng.</td></tr>
</table>
</body>
</html>"""

SAMPLE_ARTICLE_HTML = b"""<!DOCTYPE html>
<html>
<body>
<h3>1. \xe2\x80\x9cH\xe1\xbb\x93i chi\xe1\xbb\x81u tr\xe1\xbb\x9di m\xc6\xb0a\xe2\x80\x9d</h3>
<p>Tr\xc6\xb0\xe1\xbb\x9dng Giang liveshow meme.</p>
<h3>2. B\xe1\xba\xa7u c\xe1\xbb\xad m\xe1\xbb\xb9</h3>
<p>Ch\xc3\xadnh tr\xe1\xbb\x8b n\xc6\xb0\xe1\xbb\x9bc ngo\xc3\xa0i.</p>
<strong>B\xc3\xa0 n\xc3\xb3i thi\xe1\xbb\x87t h\xe1\xba\xa3 b\xc3\xa0 Th\xc6\xa1?</strong>
<strong>Thay \xc4\x91\xe1\xbb\x95i \xc4\x91\xe1\xbb\x8ba ch\xe1\xbb\x89 kh\xc3\xa1c</strong>
</body>
</html>"""


class TestSocialTrendingService(unittest.TestCase):
    """Bộ kiểm thử unit test cho SocialTrendingService."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.cache_file = os.path.join(self.temp_dir, "social_trends.json")
        self.service = SocialTrendingService(
            cache_path=self.cache_file,
            cache_ttl_seconds=3600,
            request_timeout=2.0,
            api_keys=[],  # Không gọi Gemini thật trong unit tests
        )

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_fetch_trending_keywords_api_1(self):
        """Kiểm tra API 1: Quét danh sách từ khóa thô, lọc bỏ bài chính trị và điều hướng."""
        mock_resp_ddg = MagicMock()
        mock_resp_ddg.read.return_value = SAMPLE_DDG_HTML
        mock_resp_ddg.__enter__.return_value = mock_resp_ddg

        mock_resp_article = MagicMock()
        mock_resp_article.read.return_value = SAMPLE_ARTICLE_HTML
        mock_resp_article.__enter__.return_value = mock_resp_article

        with patch("urllib.request.urlopen", side_effect=[mock_resp_ddg, mock_resp_article]):
            keywords = self.service.fetch_trending_keywords(limit=10)

        self.assertGreater(len(keywords), 0)
        self.assertTrue(any("Hồi chiều trời mưa" in kw for kw in keywords))
        for kw in keywords:
            self.assertNotIn("Bầu cử mỹ", kw)
            self.assertNotIn("Thay đổi địa chỉ", kw)

    def test_explain_trends_via_ai_api_2(self):
        """Kiểm tra API 2: Giải mã danh sách từ khóa thành ExplainedTrend / SocialTrendItem."""
        mock_ai_json = json.dumps([
            {
                "title": "Hồi chiều trời mưa",
                "origin": "Trường Giang tự trào về sự cố thời tiết",
                "emotion": "tự trào, đổ lỗi vô lý",
                "meme_syntax": "Vì hôm qua trời mưa nên [sự việc]..."
            }
        ])

        service_with_key = SocialTrendingService(
            cache_path=self.cache_file,
            api_keys=["fake-key-123"],
        )

        mock_resp = MagicMock()
        mock_resp.text = mock_ai_json

        with patch("google.genai.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.models.generate_content.return_value = mock_resp
            mock_client_cls.return_value = mock_client

            explained = service_with_key.explain_trends_via_ai(["Hồi chiều trời mưa"])

        self.assertEqual(len(explained), 1)
        self.assertEqual(explained[0].title, "Hồi chiều trời mưa")
        self.assertIn("Trường Giang", explained[0].context)
        self.assertIn("Vì hôm qua trời mưa nên", explained[0].meme_syntax)

    def test_cache_save_and_read_within_ttl(self):
        """Kiểm tra cơ chế lưu cache và đọc lại cache khi còn trong TTL mà không cần gọi mạng."""
        mock_resp_ddg = MagicMock()
        mock_resp_ddg.read.return_value = SAMPLE_DDG_HTML
        mock_resp_ddg.__enter__.return_value = mock_resp_ddg

        mock_resp_article = MagicMock()
        mock_resp_article.read.return_value = SAMPLE_ARTICLE_HTML
        mock_resp_article.__enter__.return_value = mock_resp_article

        with patch("urllib.request.urlopen", side_effect=[mock_resp_ddg, mock_resp_article]) as mock_urlopen:
            # Lần gọi 1: Chưa có cache, phải gọi mạng
            d1 = self.service.get_live_social_trends(max_items=5)
            self.assertFalse(d1.cached)

            # Lần gọi 2: Đã có cache trong thời hạn TTL, không được gọi mạng thêm lần nào
            d2 = self.service.get_live_social_trends(max_items=5)
            self.assertTrue(d2.cached)
            self.assertEqual(len(d2.items), len(d1.items))

    def test_fallback_to_stale_cache_on_network_error(self):
        """Kiểm tra khi mạng bị ngắt hoặc timeout, hệ thống tự động fallback sang đọc cache cũ."""
        os.makedirs(self.temp_dir, exist_ok=True)
        with open(self.cache_file, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "timestamp": 1000000000.0,  # Thời gian quá khứ -> hết hạn TTL
                    "fetched_at": "2026-01-01 00:00:00",
                    "items": [
                        {
                            "title": "Hồi chiều trời mưa",
                            "context": "Meme Trường Giang",
                            "meme_syntax": "Vì hôm qua trời mưa nên...",
                            "source": "TikTok / Mạng xã hội"
                        }
                    ],
                },
                f,
            )

        # Giả lập mạng bị lỗi timeout hoặc ngắt kết nối
        with patch("urllib.request.urlopen", side_effect=RuntimeError("Mất mạng / Connection timed out")):
            digest = self.service.get_live_social_trends(max_items=5)

        self.assertTrue(digest.cached)
        self.assertEqual(len(digest.items), 1)
        self.assertEqual(digest.items[0].title, "Hồi chiều trời mưa")
        self.assertEqual(digest.items[0].meme_syntax, "Vì hôm qua trời mưa nên...")

    def test_empty_digest_when_no_cache_and_network_error(self):
        """Kiểm tra khi không có mạng và hoàn toàn không có cache, hệ thống trả về rỗng minh bạch (Zero-Mock)."""
        if os.path.exists(self.cache_file):
            os.remove(self.cache_file)

        with patch("urllib.request.urlopen", side_effect=RuntimeError("Mất mạng hoàn toàn")):
            digest = self.service.get_live_social_trends(max_items=5)

        self.assertFalse(digest.cached)
        self.assertEqual(len(digest.items), 0)

    def test_to_prompt_context_formatting(self):
        """Kiểm tra hàm to_prompt_context định dạng chuẩn xác dạng bullet points cho LLM kèm cú pháp meme."""
        items = [
            SocialTrendItem(
                title="Hồi chiều trời mưa",
                context="Meme Trường Giang tự trào về thời tiết",
                meme_syntax="Vì hôm qua trời mưa nên [sự việc]...",
                source="TikTok"
            ),
            SocialTrendItem(
                title="Bà nói thiệt hả bà Thơ",
                source="Facebook"
            ),
        ]
        digest = SocialTrendDigest(items=items)
        context = digest.to_prompt_context(limit=2)

        self.assertIn('1. Trend: "Hồi chiều trời mưa" (TikTok)', context)
        self.assertIn('Bản chất & Ngữ cảnh: Meme Trường Giang tự trào về thời tiết', context)
        self.assertIn('Cú pháp biến tấu (Meme Syntax): "Vì hôm qua trời mưa nên [sự việc]..."', context)
        self.assertIn('2. Trend: "Bà nói thiệt hả bà Thơ" (Facebook)', context)


if __name__ == "__main__":
    unittest.main()
