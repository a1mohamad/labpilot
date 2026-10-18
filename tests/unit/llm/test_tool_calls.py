import json

import pytest
import responses

from labpilot.llm import (
    ClineProvider,
    GeminiProvider,
    LLMClient,
    LLMError,
    LLMResult,
    OpenAICompatibleProvider,
    Tool,
)
from labpilot.llm._calls import read_arguments, read_object

OPENAI_URL = "https://provider.test/v1/chat/completions"
GEMINI_BASE = "https://provider.test/v1beta/models"
GEMINI_URL = f"{GEMINI_BASE}/test-model:generateContent"
CLINE_URL = "https://api.cline.test/api/v1/chat/completions"

TOOL = Tool(
    name="make_plan",
    description="Choose the steps.",
    parameters={
        "type": "object",
        "properties": {
            "steps": {
                "type": "array",
                "items": {"type": "string", "enum": ["a", "b"]},
            },
            "type": {"type": "string"},
        },
        "required": ["steps"],
    },
)
ARGS = {"steps": ["a"], "type": "x"}


@pytest.fixture(autouse=True)
def key(monkeypatch):
    monkeypatch.setenv("TEST_API_KEY", "secret-key")


def openai(context_window=8_000, **extra):
    return OpenAICompatibleProvider(
        name="Test OpenAI",
        tier=1,
        url=OPENAI_URL,
        model="test/model",
        api_key_env="TEST_API_KEY",
        context_window=context_window,
        max_output_tokens=4_000,
        **extra,
    )


def gemini(**extra):
    return GeminiProvider(
        name="Test Gemini",
        tier=2,
        url=GEMINI_BASE,
        model="test-model",
        api_key_env="TEST_API_KEY",
        context_window=8_000,
        max_output_tokens=4_000,
        **extra,
    )


def cline():
    return ClineProvider(
        name="Test Cline",
        tier=3,
        url=CLINE_URL,
        model="z-ai/glm-5.3-flash",
        api_key_env="TEST_API_KEY",
        context_window=8_000,
        max_output_tokens=4_000,
    )


def openai_call(arguments, name="make_plan"):
    raw = arguments if isinstance(arguments, str) else json.dumps(arguments)
    call = {
        "id": "c1",
        "type": "function",
        "function": {"name": name, "arguments": raw},
    }
    return {
        "model": "test/model-v2",
        "choices": [
            {
                "message": {"content": None, "tool_calls": [call]},
                "finish_reason": "tool_calls",
            }
        ],
    }


def openai_text(content):
    return {
        "model": "test/model-v2",
        "choices": [{"message": {"content": content}, "finish_reason": "stop"}],
    }


def gemini_call(args, name="make_plan"):
    return {
        "modelVersion": "test-model-001",
        "candidates": [
            {
                "content": {"parts": [{"functionCall": {"name": name, "args": args}}]},
                "finishReason": "STOP",
            }
        ],
    }


def gemini_text(text):
    return {
        "modelVersion": "test-model-001",
        "candidates": [
            {"content": {"parts": [{"text": text}]}, "finishReason": "STOP"}
        ],
    }


def sent():
    return json.loads(responses.calls[0].request.body)


@pytest.mark.parametrize(
    "text",
    [
        '{"a": 1}',
        '```json\n{"a": 1}\n```',
        'Here is the plan: {"a": 1} I hope it helps.',
    ],
    ids=["plain", "code fence", "words around"],
)
def test_an_object_is_found_in_the_text(text):
    assert read_object(text, "src") == {"a": 1}


def test_an_object_cut_short_is_refused_even_when_a_smaller_one_sits_inside():
    cut = '{"steps": ["a"], "queries": [{"side": "A", "text": "x"}'

    with pytest.raises(LLMError, match="not valid"):
        read_object(cut, "src")


@pytest.mark.parametrize("text", ["I cannot help with that.", "[1, 2]"])
def test_an_answer_without_an_object_is_refused(text):
    with pytest.raises(LLMError, match="no JSON object"):
        read_object(text, "src")


@pytest.mark.parametrize("raw", ['{"a": 1}', {"a": 1}], ids=["text", "object"])
def test_function_arguments_may_come_as_text_or_as_an_object(raw):
    assert read_arguments(raw, "src") == {"a": 1}


@pytest.mark.parametrize("raw", ["", "not json", "[1]", 5, None])
def test_function_arguments_that_are_not_an_object_are_refused(raw):
    with pytest.raises(LLMError):
        read_arguments(raw, "src")


@responses.activate
def test_the_openai_shape_gets_the_tool_in_its_own_format():
    responses.post(OPENAI_URL, json=openai_call(ARGS))

    openai().complete("choose", tool=TOOL)

    assert sent()["tools"] == [
        {
            "type": "function",
            "function": {
                "name": "make_plan",
                "description": "Choose the steps.",
                "parameters": TOOL.parameters,
            },
        }
    ]


@responses.activate
def test_nothing_about_tools_is_sent_without_a_tool():
    responses.post(OPENAI_URL, json=openai_text("hello"))

    openai().complete("choose")

    assert "tools" not in sent()
    assert sent()["messages"] == [{"role": "user", "content": "choose"}]


@responses.activate
def test_the_prompt_also_asks_for_json_in_case_the_tier_ignores_tools():
    responses.post(OPENAI_URL, json=openai_call(ARGS))

    openai().complete("choose", tool=TOOL)

    content = sent()["messages"][0]["content"]
    assert content.startswith("choose")
    assert "make_plan" in content
    assert json.dumps(TOOL.parameters) in content


@responses.activate
def test_a_function_call_becomes_the_arguments_of_the_result():
    responses.post(OPENAI_URL, json=openai_call(ARGS))

    result = openai().complete("choose", tool=TOOL)

    assert isinstance(result, LLMResult)
    assert result.arguments == ARGS
    assert json.loads(result.text) == ARGS
    assert result.finish_reason == "tool_calls"
    assert result.model == "test/model-v2"
    assert result.tier == 1


@responses.activate
def test_a_call_to_another_function_is_a_failed_tier():
    responses.post(OPENAI_URL, json=openai_call(ARGS, name="delete_everything"))

    with pytest.raises(LLMError, match="delete_everything"):
        openai().complete("choose", tool=TOOL)


@responses.activate
def test_arguments_that_are_not_json_are_a_failed_tier():
    responses.post(OPENAI_URL, json=openai_call("steps: a"))

    with pytest.raises(LLMError, match="not JSON"):
        openai().complete("choose", tool=TOOL)


@pytest.mark.parametrize(
    "content",
    ['{"steps": ["a"], "type": "x"}', '```json\n{"steps": ["a"], "type": "x"}\n```'],
    ids=["plain", "code fence"],
)
@responses.activate
def test_a_tier_that_answers_in_text_is_read_as_json(content):
    responses.post(OPENAI_URL, json=openai_text(content))

    assert openai().complete("choose", tool=TOOL).arguments == ARGS


@responses.activate
def test_a_text_answer_without_json_is_a_failed_tier():
    responses.post(OPENAI_URL, json=openai_text("You should read the paper first."))

    with pytest.raises(LLMError, match="no JSON object"):
        openai().complete("choose", tool=TOOL)


@responses.activate
def test_a_reply_with_no_call_and_no_text_is_a_failed_tier():
    responses.post(OPENAI_URL, json=openai_text(None))

    with pytest.raises(LLMError, match="empty answer"):
        openai().complete("choose", tool=TOOL)


@responses.activate
def test_without_a_tool_the_arguments_stay_empty():
    responses.post(OPENAI_URL, json=openai_text('{"steps": []}'))

    assert openai().complete("choose").arguments is None


@responses.activate
def test_gemini_gets_the_tool_with_upper_case_types():
    responses.post(GEMINI_URL, json=gemini_call(ARGS))

    gemini().complete("choose", tool=TOOL)

    assert sent()["tools"] == [
        {
            "functionDeclarations": [
                {
                    "name": "make_plan",
                    "description": "Choose the steps.",
                    "parameters": {
                        "type": "OBJECT",
                        "properties": {
                            "steps": {
                                "type": "ARRAY",
                                "items": {"type": "STRING", "enum": ["a", "b"]},
                            },
                            "type": {"type": "STRING"},
                        },
                        "required": ["steps"],
                    },
                }
            ]
        }
    ]


@responses.activate
def test_the_tool_we_hand_over_is_not_changed_by_the_translation():
    responses.post(GEMINI_URL, json=gemini_call(ARGS))

    gemini().complete("choose", tool=TOOL)

    assert TOOL.parameters["type"] == "object"


@responses.activate
def test_gemini_sends_no_tools_without_a_tool():
    responses.post(GEMINI_URL, json=gemini_text("hello"))

    gemini().complete("choose")

    assert "tools" not in sent()


@responses.activate
def test_a_gemini_function_call_becomes_the_arguments_of_the_result():
    responses.post(GEMINI_URL, json=gemini_call(ARGS))

    result = gemini().complete("choose", tool=TOOL)

    assert result.arguments == ARGS
    assert json.loads(result.text) == ARGS
    assert result.finish_reason == "STOP"
    assert result.model == "test-model-001"


@responses.activate
def test_a_gemini_call_without_arguments_gives_an_empty_object():
    body = gemini_call({})
    del body["candidates"][0]["content"]["parts"][0]["functionCall"]["args"]
    responses.post(GEMINI_URL, json=body)

    assert gemini().complete("choose", tool=TOOL).arguments == {}


@responses.activate
def test_a_gemini_call_to_another_function_is_a_failed_tier():
    responses.post(GEMINI_URL, json=gemini_call(ARGS, name="other"))

    with pytest.raises(LLMError, match="'other'"):
        gemini().complete("choose", tool=TOOL)


@responses.activate
def test_gemma_wraps_json_in_a_code_fence_and_it_is_still_read():
    fenced = '```json\n{"steps": ["a"], "type": "x"}\n```'
    responses.post(GEMINI_URL, json=gemini_text(fenced))

    assert gemini().complete("choose", tool=TOOL).arguments == ARGS


@responses.activate
def test_a_gemini_text_answer_without_json_is_a_failed_tier():
    responses.post(GEMINI_URL, json=gemini_text("No plan today."))

    with pytest.raises(LLMError, match="no JSON object"):
        gemini().complete("choose", tool=TOOL)


@responses.activate
def test_cline_reads_a_call_inside_its_envelope():
    responses.post(CLINE_URL, json={"data": openai_call(ARGS), "success": True})

    assert cline().complete("choose", tool=TOOL).arguments == ARGS


@responses.activate
def test_the_added_instruction_counts_against_the_context_window():
    responses.post(OPENAI_URL, json=openai_text("hello"))
    small = openai(context_window=60)
    prompt = "x" * 30

    small.complete(prompt, max_tokens=1)

    with pytest.raises(LLMError, match="context window"):
        small.complete(prompt, max_tokens=1, tool=TOOL)
    assert len(responses.calls) == 1


class FakeProvider:
    name = "Fake"
    tier = 1
    api_key_env = "TEST_API_KEY"
    pool = "TEST_API_KEY"

    def __init__(self):
        self.tool = "never called"

    def complete(self, prompt, *, max_tokens=1024, tool=None):
        self.tool = tool
        return LLMResult(text="{}", model=self.name, tier=self.tier, arguments={})


def test_the_chain_hands_the_tool_to_the_provider():
    fake = FakeProvider()

    LLMClient(chain=(fake,)).generate("choose", tool=TOOL)

    assert fake.tool is TOOL


def test_the_chain_hands_no_tool_when_none_was_given():
    fake = FakeProvider()

    LLMClient(chain=(fake,)).generate("choose")

    assert fake.tool is None


@responses.activate
def test_a_tier_whose_answer_cannot_be_read_hands_over_to_the_next_tier():
    responses.post(OPENAI_URL, json=openai_text("Let me think about that."))
    responses.post(GEMINI_URL, json=gemini_call(ARGS))

    result = LLMClient(chain=(openai(), gemini()), base_delay=0.0).generate(
        "choose", tool=TOOL
    )

    assert result.arguments == ARGS
    assert result.tier == 2
    assert len(result.attempts) == 1
    assert "no JSON object" in result.attempts[0].error
