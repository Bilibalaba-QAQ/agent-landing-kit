#!/usr/bin/env python3
"""Confluence 渲染后 HTML(body.view)→ markdown 风格纯文本。零第三方依赖。

给「读」用:agent 读页面时要的是能看懂、能再加工的结构化文本,不是一坨 XHTML。
与 browser_transport 内嵌 JS 的 ser() 对应(一 python 一 JS,改一处须同步另一处)。
"""

import re
from html.parser import HTMLParser

__all__ = ["view_to_text"]

_SKIP = {"script", "style", "head"}
_INLINE_WRAP = {"strong": "**", "b": "**", "em": "*", "i": "*", "code": "`"}
_INDENT = "\x01"   # 列表缩进哨兵,收尾还原为两个空格


class _Conv(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out = []
        self.skip = 0
        self.list_stack = []      # 'ul' / 'ol'
        self.table = None         # 收集中的表格 rows
        self.row = None
        self.cell = None
        self.href = None

    # ---- 输出helpers ----
    def _emit(self, s):
        if self.cell is not None:
            self.cell.append(s)
        else:
            self.out.append(s)

    def handle_starttag(self, tag, attrs):
        if tag in _SKIP:
            self.skip += 1
            return
        if self.skip:
            return
        a = dict(attrs)
        if re.fullmatch(r"h[1-6]", tag):
            self._emit("\n\n" + "#" * int(tag[1]) + " ")
        elif tag == "p":
            self._emit("\n\n")
        elif tag == "br":
            self._emit("\n")
        elif tag == "hr":
            self._emit("\n\n---\n")
        elif tag in ("ul", "ol"):
            if not self.list_stack:      # 顶层列表前空一行,与段落隔开
                self._emit("\n")
            self.list_stack.append(tag)
        elif tag == "li":
            depth = max(0, len(self.list_stack) - 1)
            marker = "1. " if (self.list_stack and self.list_stack[-1] == "ol") else "- "
            # 缩进先用哨兵占位,免得被后面的空白归一化吃掉,收尾再还原成空格
            self._emit("\n" + _INDENT * depth + marker)
        elif tag == "table":
            self.table = []
        elif tag == "tr" and self.table is not None:
            self.row = []
        elif tag in ("td", "th") and self.row is not None:
            self.cell = []
        elif tag == "pre":
            self._emit("\n\n```\n")
        elif tag in _INLINE_WRAP:
            self._emit(_INLINE_WRAP[tag])
        elif tag == "a":
            self.href = a.get("href")
            self._emit("[")
        elif tag == "img":
            # 只留 alt(内部 URL 又长又无用);无 alt 的多是附件图标/表情,纯噪音,直接丢
            if (a.get("alt") or "").strip():
                self._emit("![%s]" % a["alt"].strip())

    def handle_endtag(self, tag):
        if tag in _SKIP:
            self.skip = max(0, self.skip - 1)
            return
        if self.skip:
            return
        if tag in ("ul", "ol"):
            if self.list_stack:
                self.list_stack.pop()
            if not self.list_stack:
                self._emit("\n")
        elif tag in ("td", "th") and self.cell is not None:
            self.row.append("".join(self.cell).strip().replace("|", "\\|"))
            self.cell = None
        elif tag == "tr" and self.row is not None:
            self.table.append(self.row)
            self.row = None
        elif tag == "table" and self.table is not None:
            rows, self.table = self.table, None
            if rows:
                self.out.append("\n\n| " + " | ".join(rows[0]) + " |")
                self.out.append("\n|" + "|".join("---" for _ in rows[0]) + "|")
                for r in rows[1:]:
                    self.out.append("\n| " + " | ".join(r) + " |")
                self.out.append("\n")
        elif tag == "pre":
            self._emit("\n```\n")
        elif tag in _INLINE_WRAP:
            self._emit(_INLINE_WRAP[tag])
        elif tag == "a":
            self._emit("](%s)" % self.href if self.href else "]")
            self.href = None

    def handle_data(self, data):
        if self.skip:
            return
        self._emit(re.sub(r"[ \t\r\n]+", " ", data))


def view_to_text(html):
    c = _Conv()
    c.feed(html or "")
    text = "".join(c.out)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"[ \t]*\n[ \t]*", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    # 图片被链接包住时(Confluence 附件常见)去掉外层链接,只留图片本身
    text = re.sub(r"\[(!\[[^\]]*\])\]\([^)]*\)", r"\1", text)
    return text.strip().replace(_INDENT, "  ")


if __name__ == "__main__":
    import sys
    src = sys.stdin.read() if len(sys.argv) < 2 or sys.argv[1] == "-" \
        else open(sys.argv[1], encoding="utf-8").read()
    print(view_to_text(src))
