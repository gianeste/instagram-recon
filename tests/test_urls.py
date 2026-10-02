import pytest

from instagram_collector.urls import PostURLParseError, UnsupportedContentType, parse_post_url


def test_parse_post_and_reel_urls():
    post = parse_post_url("https://www.instagram.com/p/DdeY69zlNuQ/?img_index=1")
    assert post.shortcode == "DdeY69zlNuQ"
    assert post.content_type == "post"
    assert post.canonical_url == "https://www.instagram.com/p/DdeY69zlNuQ/?img_index=1"

    reel = parse_post_url("https://instagram.com/reel/AbcDE_12345")
    assert reel.content_type == "reel"
    assert reel.canonical_url == "https://www.instagram.com/reel/AbcDE_12345/"


def test_parse_username_prefixed_post_url():
    post = parse_post_url("https://www.instagram.com/nytimes/p/Dd7eoFRE5_t/")
    assert post.shortcode == "Dd7eoFRE5_t"
    assert post.canonical_url == "https://www.instagram.com/p/Dd7eoFRE5_t/"


@pytest.mark.parametrize(
    "url,error",
    [
        ("https://example.com/p/DdeY69zlNuQ", PostURLParseError),
        ("https://instagram.com/p/not-a-valid-code!", PostURLParseError),
        ("https://instagram.com/tv/DdeY69zlNuQ", UnsupportedContentType),
        ("https://instagram.com/p/DdeY69zlNuQ?img_index=0", PostURLParseError),
    ],
)
def test_reject_unsupported_or_malformed_urls(url, error):
    with pytest.raises(error):
        parse_post_url(url)
