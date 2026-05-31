"""JSON extraction from messy model output (synth/jsonio.py)."""

import pytest

from myAIstory.synth.jsonio import JSONExtractError, extract_json


def test_plain_object():
    assert extract_json('{"a": 1}') == {"a": 1}


def test_fenced_object():
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}


def test_prose_wrapped_object():
    text = 'Sure! Here is your bible:\n{"a": 1, "b": [2, 3]}\nHope that helps.'
    assert extract_json(text) == {"a": 1, "b": [2, 3]}


def test_nested_braces_balanced():
    assert extract_json('{"a": {"b": {"c": 1}}}') == {"a": {"b": {"c": 1}}}


def test_brace_inside_string_ignored():
    assert extract_json('{"text": "a } b { c"}') == {"text": "a } b { c"}


def test_no_object_raises():
    with pytest.raises(JSONExtractError):
        extract_json("there is no json here")


def test_malformed_raises():
    with pytest.raises(JSONExtractError):
        extract_json('{"a": }')
