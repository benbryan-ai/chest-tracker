import re
from pathlib import Path

from chest_tracker.group import protocol
PAGE = (Path(__file__).resolve().parent.parent / "console" / "index.html").read_text(encoding="utf-8")


def test_page_message_matches_protocol():
    # the page builds "\u{1F4E6} chests (+N)"; make sure it is the text the bot parses
    assert '"\\u{1F4E6} chests ("' in PAGE
    for amount in (1, 5, -1):
        text = "\U0001F4E6 chests (" + ("+" if amount >= 0 else "-") + str(abs(amount)) + ")"
        assert text == protocol.format_delta(amount)
        assert protocol.parse_delta(text) == amount


def test_page_webhook_pattern_accepts_real_urls():
    pattern = re.search(r"const HOOK = /(.*)/;", PAGE).group(1).replace("\\/", "/")
    assert re.fullmatch(pattern.replace("(?:", "(?:"), "https://discord.com/api/webhooks/123/abc-DEF_1")
    assert not re.fullmatch(pattern, "https://evil.example/api/webhooks/123/abc")
    assert protocol.is_webhook_url("https://discord.com/api/webhooks/123/abc-DEF_1")
