"""Unit tests for pure utility functions in vanna/app.py."""
import json
import pytest
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

from app import _trim_to_user_turn, _strip_explore_rows


# ── helpers ───────────────────────────────────────────────────────────────────

def user_msg(text='hello'):
    return ModelRequest(parts=[UserPromptPart(content=text)])


def tool_return(name, content):
    return ModelRequest(parts=[ToolReturnPart(tool_name=name, content=content, tool_call_id='tc1')])


def tool_call(name, args_dict):
    return ModelResponse(parts=[ToolCallPart(tool_name=name, args=json.dumps(args_dict), tool_call_id='tc1')])


# ── _trim_to_user_turn ────────────────────────────────────────────────────────

def test_trim_empty_list():
    assert _trim_to_user_turn([]) == []


def test_trim_already_clean():
    msgs = [user_msg('what is revenue?'), tool_return('explore_data', {'sql': 'SELECT 1', 'row_count': 1})]
    assert _trim_to_user_turn(msgs) == msgs


def test_trim_orphaned_tool_return_at_start():
    orphan = tool_return('explore_data', {'sql': 'SELECT 1'})
    clean = user_msg('follow-up question')
    result = _trim_to_user_turn([orphan, clean])
    assert result == [clean]


def test_trim_no_user_prompt_returns_empty():
    msgs = [tool_return('explore_data', {'sql': 'SELECT 1'})]
    assert _trim_to_user_turn(msgs) == []


# ── _strip_explore_rows ───────────────────────────────────────────────────────

def test_strip_removes_rows_from_explore_data():
    content = {'sql': 'SELECT 1', 'row_count': 3, 'rows': [{'a': 1}, {'a': 2}, {'a': 3}]}
    msgs = [tool_return('explore_data', content)]
    result = _strip_explore_rows(msgs)
    stripped_content = result[0].parts[0].content
    assert 'rows' not in stripped_content
    assert stripped_content['sql'] == 'SELECT 1'
    assert stripped_content['row_count'] == 3


def test_strip_leaves_non_explore_tool_returns_unchanged():
    content = {'result': 'some result'}
    msgs = [tool_return('other_tool', content)]
    result = _strip_explore_rows(msgs)
    assert result[0].parts[0].content == content


def test_strip_removes_data_from_final_result_args():
    args = {'intent': 'explore', 'text': 'Here is the data.', 'data': [{'x': 1}]}
    msgs = [tool_call('final_result', args)]
    result = _strip_explore_rows(msgs)
    stripped_args = json.loads(result[0].parts[0].args)
    assert stripped_args['data'] is None
    assert stripped_args['intent'] == 'explore'
    assert stripped_args['text'] == 'Here is the data.'
