"""Turning the web plugin's 【domain】 markers into real links.

The plugin emits citations as a bare domain in fullwidth brackets, which
renders as text that looks clickable but isn't. The matching URLs come back
in message.annotations; these pin how the two get paired up.
"""
import pytest

from app.llm import _citation_urls, link_citations

PM = "https://www.pmindia.gov.in/en/pms-profile/"
WIKI = "https://en.wikipedia.org/wiki/Narendra_Modi"


def test_marker_becomes_a_link_to_the_deep_url():
    out = link_citations(
        "Narendra Modi is the Prime Minister of India【pmindia.gov.in】",
        [PM])
    assert out == (
        f"Narendra Modi is the Prime Minister of India[pmindia.gov.in]({PM})")


def test_multiple_markers_each_match_their_own_host():
    out = link_citations("Modi【pmindia.gov.in】【wikipedia.org】", [PM, WIKI])
    assert f"[pmindia.gov.in]({PM})" in out
    assert f"[wikipedia.org]({WIKI})" in out


def test_subdomain_marker_matches_parent_annotation():
    # annotation host is en.wikipedia.org, marker says wikipedia.org
    out = link_citations("x【wikipedia.org】", [WIKI])
    assert f"[wikipedia.org]({WIKI})" in out


def test_unmatched_marker_is_left_alone():
    # Linking an unmatched domain would be a guess; a wrong link is worse
    # than a plain one, so the marker survives untouched.
    out = link_citations("x【example.com】", [PM])
    assert out == "x【example.com】"


def test_no_annotations_is_a_no_op():
    assert link_citations("x【pmindia.gov.in】", []) == "x【pmindia.gov.in】"


def test_text_without_markers_is_unchanged():
    assert link_citations("plain answer", [PM]) == "plain answer"


def test_existing_markdown_links_are_untouched():
    src = "see [the profile](https://a.example) for more"
    assert link_citations(src, [PM]) == src


@pytest.mark.parametrize("annotations,expected", [
    (None, []),
    ([], []),
    ([{"type": "url_citation", "url_citation": {"url": PM}}], [PM]),
    # duplicates collapse
    ([{"url_citation": {"url": PM}}, {"url_citation": {"url": PM}}], [PM]),
    # junk shapes are skipped rather than raising
    (["nonsense", {"url_citation": {}}, {"url_citation": {"url": "ftp://x"}}], []),
])
def test_citation_urls_extraction(annotations, expected):
    assert _citation_urls(annotations) == expected
