"""Data models for real-time social media trends."""
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class ExplainedTrend:
    """Đại diện cho 1 trend/drama mạng xã hội đã được phân tích ngữ cảnh và cú pháp meme."""
    keyword: str
    origin: str = ""
    emotion: str = ""
    meme_syntax: str = ""
    source: str = "Mạng xã hội"


@dataclass
class SocialTrendItem:
    """Đại diện cho 1 câu nói viral, drama hoặc chủ đề đang bão mạng xã hội."""
    title: str
    context: str = ""
    source: str = "Mạng xã hội"
    link: str = ""
    published: str = ""
    meme_syntax: str = ""


@dataclass
class SocialTrendDigest:
    """Tập hợp các xu hướng bão mạng xã hội thời gian thực được tinh lọc."""
    items: List[SocialTrendItem] = field(default_factory=list)
    fetched_at: str = ""
    cached: bool = False

    def to_prompt_context(self, limit: int = 6) -> str:
        """Định dạng danh sách trend kèm ngữ cảnh và cú pháp meme để LLM hiểu và làm cầu nối tự nhiên."""
        if not self.items:
            return "- Hiện tại không có trend mạng xã hội nổi bật; ưu tiên dùng Hook tò mò, phản trực giác hoặc bóc phốt đời thực."

        selected = self.items[:limit]
        lines = []
        for i, item in enumerate(selected, start=1):
            source_tag = f" ({item.source})" if item.source else ""
            parts = [f'{i}. Trend: "{item.title}"{source_tag}']
            if item.context and item.context.strip():
                parts.append(f'   - Bản chất & Ngữ cảnh: {item.context.strip()}')
            if item.meme_syntax and item.meme_syntax.strip():
                parts.append(f'   - Cú pháp biến tấu (Meme Syntax): "{item.meme_syntax.strip()}"')
            lines.append("\n".join(parts))
        return "\n\n".join(lines)
