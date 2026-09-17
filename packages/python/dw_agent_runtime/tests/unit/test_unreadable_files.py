"""Một khối tệp mô hình không đọc được không được phép giết cả lượt.

Đo được 2026-09-08 trên stack thật: `document.save` ghi một .docx vào thư mục
làm việc, mô hình gọi `read_file` lên chính tệp đó, middleware filesystem trả
về một khối file và đoán MIME là `application/octet-stream`. Nhà cung cấp từ
chối NGUYÊN CẢ REQUEST:

    openai.BadRequestError: Error code: 400 - Invalid file data:
    'input[113].output[0].file_data' ... unsupported MIME type
    'application/octet-stream'

Một khối trong hàng trăm, và cả lượt mất trắng. Đây không phải một tool hỏng mà
mô hình trả lời thay được - lỗi nổ ở chính lời gọi model.

Sửa ở tầng này chứ không ở quyền filesystem, vì `deepagents` từ chối dựng
middleware có cả `execute` lẫn luật đụng ra ngoài route, và nó đúng: khi mô
hình có shell thì cấm `read_file` một đường dẫn là hình thức, `cat` không đi
qua file tool nào cả.
"""

from __future__ import annotations

from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from dw_agent_runtime.adapters.langchain_tools import (
    UnreadableFilesMiddleware,
    _without_unreadable_files,
)

pytestmark = pytest.mark.unit

DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _content(message: Any) -> list[Any]:
    return list(message.content)


def test_an_unknown_binary_becomes_a_sentence_the_model_can_act_on() -> None:
    message = HumanMessage(
        content=[
            {"type": "text", "text": "đây là tệp"},
            {
                "type": "file",
                "mime_type": "application/octet-stream",
                "filename": "bao-cao.docx",
                "file_data": "data:application/octet-stream;base64,UEs=",
            },
        ]
    )

    cleaned = _content(_without_unreadable_files(message))

    assert len(cleaned) == 2
    assert cleaned[0] == {"type": "text", "text": "đây là tệp"}
    assert cleaned[1]["type"] == "text"
    # Tên tệp phải còn, nếu không mô hình không biết nó vừa đọc phải cái gì và
    # sẽ đọc lại.
    assert "bao-cao.docx" in cleaned[1]["text"]
    assert "application/octet-stream" in cleaned[1]["text"]


def test_a_docx_is_replaced_even_when_the_mime_is_named_correctly() -> None:
    """Đúng tên MIME không có nghĩa là mô hình đọc được.

    Một .docx là zip nén; nhà cung cấp cũng từ chối, và nếu không thì mô hình
    cũng chỉ nhận được bytes.
    """
    message = HumanMessage(
        content=[{"type": "file", "mime_type": DOCX, "filename": "x.docx", "file_data": "d"}]
    )

    cleaned = _content(_without_unreadable_files(message))

    assert cleaned[0]["type"] == "text"


def test_a_pdf_passes_through_untouched() -> None:
    """Danh sách là allow-list, không phải deny-list: PDF thì mô hình đọc được."""
    block = {"type": "file", "mime_type": "application/pdf", "file_data": "d"}
    message = HumanMessage(content=[block])

    # Bằng nhau chứ không phải cùng một object: pydantic sao chép content khi
    # dựng message, nên `is` sẽ đo cái khác chứ không đo "không đổi".
    assert _content(_without_unreadable_files(message))[0] == block


def test_the_mime_is_read_out_of_a_data_url_when_no_field_carries_it() -> None:
    """Hai hình dạng vì hai đời API; chỉ đọc `mime_type` là bỏ sót một nửa."""
    message = HumanMessage(
        content=[{"type": "file", "file_data": "data:application/octet-stream;base64,UEs="}]
    )

    assert _content(_without_unreadable_files(message))[0]["type"] == "text"


def test_a_message_with_nothing_to_clean_is_returned_as_it_was() -> None:
    """Cùng một object, không phải bản sao.

    `model_copy` giữ id và metadata, nhưng dựng lại mọi message trên mọi lời
    gọi là công vô ích trên đường nóng nhất của một lượt.
    """
    message = AIMessage(content="chỉ là chữ")

    assert _without_unreadable_files(message) is message


@pytest.mark.asyncio
async def test_the_middleware_hands_the_handler_the_cleaned_messages() -> None:
    seen: dict[str, Any] = {}

    class _Request:
        def __init__(self, messages: list[Any]) -> None:
            self.messages = messages

        def override(self, **changes: Any) -> _Request:
            return _Request(changes["messages"])

    async def handler(request: Any) -> str:
        seen["messages"] = request.messages
        return "ok"

    dirty = HumanMessage(
        content=[{"type": "file", "mime_type": "application/octet-stream", "file_data": "d"}]
    )
    result = await UnreadableFilesMiddleware().awrap_model_call(
        _Request([dirty]),  # type: ignore[arg-type]
        handler,
    )

    assert result == "ok"
    assert seen["messages"][0].content[0]["type"] == "text"
