#!/usr/bin/env python3
"""markdown → Confluence storage format(XHTML)转换器。零第三方依赖。

storage format 是 Confluence 页面正文的原生存储格式:XHTML 子集 + `ac:` / `ri:` 命名空间宏。
本模块只做「文本 → storage」的纯函数转换,不碰网络,可独立测试。

支持:标题 / 段落 / 有序无序列表(含嵌套)/ 代码块(code 宏)/ 表格 / 引用 /
      GFM 提示块(> [!NOTE] → info 宏)/ 分割线 / 目录([TOC] → toc 宏)/
      行内粗斜体·行内代码·链接·图片·删除线 / 原样直通(```storage 围栏)。
"""

import html
import re

__all__ = ["md_to_storage"]

# Confluence code 宏支持的语言名;左边是常见 markdown 别名。
_CODE_LANG = {
    "js": "javascript", "jsx": "javascript", "ts": "javascript", "tsx": "javascript",
    "py": "python", "python3": "python",
    "sh": "bash", "shell": "bash", "zsh": "bash", "console": "bash",
    "yml": "yaml", "md": "none", "markdown": "none", "text": "none", "txt": "none",
    "html": "xml", "xhtml": "xml", "vue": "xml",
    "c": "cpp", "h": "cpp", "objc": "cpp", "go": "none", "rust": "none",
}

# GFM 提示块 → Confluence 宏名
_ADMONITION = {
    "note": "note", "tip": "tip", "important": "info",
    "warning": "warning", "caution": "warning", "info": "info",
}

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_FENCE_RE = re.compile(r"^(```|~~~)\s*([\w+-]*)\s*$")
_HR_RE = re.compile(r"^\s{0,3}([-*_])\s*(?:\1\s*){2,}$")
_LIST_RE = re.compile(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$")
_QUOTE_RE = re.compile(r"^\s{0,3}>\s?(.*)$")
_ALERT_RE = re.compile(r"^\[!(\w+)\]\s*$", re.I)
_TABLE_SEP_RE = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")


def _esc(text):
    """文本节点转义。属性值另用 _esc_attr。"""
    return html.escape(text, quote=False)


def _esc_attr(text):
    return html.escape(text, quote=True)


def _attr(escaped):
    """把已经过 _esc 的文本再补足属性位转义(只剩引号未处理)。"""
    return escaped.replace('"', "&quot;")


def _cdata(text):
    """CDATA 包裹;内容自身含 ']]>' 时按规范切断再拼接。"""
    return "<![CDATA[" + text.replace("]]>", "]]]]><![CDATA[>") + "]]>"


def _code_macro(lang, body):
    lang = _CODE_LANG.get(lang.lower(), lang.lower()) if lang else "none"
    parts = ['<ac:structured-macro ac:name="code" ac:schema-version="1">']
    if lang:
        parts.append('<ac:parameter ac:name="language">%s</ac:parameter>' % _esc(lang))
    parts.append("<ac:plain-text-body>%s</ac:plain-text-body>" % _cdata(body))
    parts.append("</ac:structured-macro>")
    return "".join(parts)


# ---------- 行内 ----------

def _inline(text):
    """行内标记转换。先整体转义,再逐项替换成标签;代码片段与链接先占位保护。"""
    text = _esc(text)
    slots = []

    def _stash(markup):
        slots.append(markup)
        return "\x00%d\x00" % (len(slots) - 1)

    # 图片:![alt](url)
    text = re.sub(
        r"!\[([^\]]*)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)",
        lambda m: _stash('<ac:image ac:alt="%s"><ri:url ri:value="%s"/></ac:image>'
                         % (_attr(m.group(1)), _attr(m.group(2)))),
        text,
    )
    # 链接:[text](url)
    text = re.sub(
        r"\[([^\]]+)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)",
        lambda m: _stash('<a href="%s">%s</a>' % (_attr(m.group(2)), m.group(1))),
        text,
    )
    # 行内代码(内容不再参与其余行内规则)
    text = re.sub(r"`([^`]+)`", lambda m: _stash("<code>%s</code>" % m.group(1)), text)
    # 粗体 / 斜体 / 删除线
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<em>\1</em>", text)
    text = re.sub(r"(?<![\w_])_(?!\s)(.+?)(?<!\s)_(?![\w_])", r"<em>\1</em>", text)
    text = re.sub(r"~~(.+?)~~",
                  r'<span style="text-decoration: line-through;">\1</span>', text)

    return re.sub(r"\x00(\d+)\x00", lambda m: slots[int(m.group(1))], text)


# ---------- 块级 ----------

def _render_list(items, start, level, ordered):
    """items 为 (indent, marker, text) 列表;按缩进递归生成嵌套列表。"""
    tag = "ol" if ordered else "ul"
    out = ["<%s>" % tag]
    i = start
    while i < len(items):
        indent, marker, text = items[i]
        if indent < level:
            break
        if indent > level:  # 交由上一层的 li 收纳,这里不应发生
            i += 1
            continue
        body = [_inline(text)]
        j = i + 1
        if j < len(items) and items[j][0] > level:
            child_ordered = items[j][1][0].isdigit()
            sub, j = _render_list(items, j, items[j][0], child_ordered)
            body.append(sub)
        out.append("<li>%s</li>" % "".join(body))
        i = j
    out.append("</%s>" % tag)
    return "".join(out), i


def _render_table(rows):
    """rows[0] 为表头。"""
    out = ["<table><tbody>"]
    for idx, cells in enumerate(rows):
        cell_tag = "th" if idx == 0 else "td"
        out.append("<tr>")
        for c in cells:
            out.append("<%s>%s</%s>" % (cell_tag, _inline(c) or "&nbsp;", cell_tag))
        out.append("</tr>")
    out.append("</tbody></table>")
    return "".join(out)


def _split_row(line):
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    return [c.strip() for c in line.split("|")]


def _render_quote(lines):
    """引用块;首行为 [!TYPE] 时转成对应 Confluence 宏。"""
    macro = None
    if lines:
        m = _ALERT_RE.match(lines[0].strip())
        if m:
            macro = _ADMONITION.get(m.group(1).lower())
            if macro:
                lines = lines[1:]
    inner = md_to_storage("\n".join(lines))
    if macro:
        return ('<ac:structured-macro ac:name="%s" ac:schema-version="1">'
                "<ac:rich-text-body>%s</ac:rich-text-body></ac:structured-macro>"
                % (macro, inner))
    return "<blockquote>%s</blockquote>" % inner


def md_to_storage(md):
    """markdown 文本 → Confluence storage format 字符串。"""
    lines = md.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    out = []
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]

        if not line.strip():
            i += 1
            continue

        # 代码围栏(语言为 storage/confluence 时原样直通)
        m = _FENCE_RE.match(line.strip())
        if m:
            fence, lang = m.group(1), m.group(2)
            body = []
            i += 1
            while i < n and lines[i].strip() != fence:
                body.append(lines[i])
                i += 1
            i += 1  # 跳过收尾围栏
            raw = "\n".join(body)
            if lang.lower() in ("storage", "confluence"):
                out.append(raw)
            else:
                out.append(_code_macro(lang, raw))
            continue

        # 目录宏
        if line.strip().upper() == "[TOC]":
            out.append('<ac:structured-macro ac:name="toc" ac:schema-version="1"/>')
            i += 1
            continue

        # 分割线(须先于列表判断,避免 --- 被当成无序项)
        if _HR_RE.match(line):
            out.append("<hr/>")
            i += 1
            continue

        # 标题
        m = _HEADING_RE.match(line)
        if m:
            level = len(m.group(1))
            out.append("<h%d>%s</h%d>" % (level, _inline(m.group(2).strip()), level))
            i += 1
            continue

        # 引用 / 提示块
        if _QUOTE_RE.match(line):
            buf = []
            while i < n and _QUOTE_RE.match(lines[i]):
                buf.append(_QUOTE_RE.match(lines[i]).group(1))
                i += 1
            out.append(_render_quote(buf))
            continue

        # 表格(当前行含 | 且下一行是分隔行)
        if "|" in line and i + 1 < n and _TABLE_SEP_RE.match(lines[i + 1]):
            rows = [_split_row(line)]
            i += 2
            while i < n and "|" in lines[i] and lines[i].strip():
                rows.append(_split_row(lines[i]))
                i += 1
            out.append(_render_table(rows))
            continue

        # 列表
        m = _LIST_RE.match(line)
        if m:
            items = []
            while i < n:
                mm = _LIST_RE.match(lines[i])
                if not mm:
                    break
                items.append((len(mm.group(1)), mm.group(2), mm.group(3)))
                i += 1
            base = items[0][0]
            ordered = items[0][1][0].isdigit()
            markup, _ = _render_list(items, 0, base, ordered)
            out.append(markup)
            continue

        # 段落(连续非空行,遇到其他块级起手式即止)
        buf = []
        while i < n and lines[i].strip():
            cur = lines[i]
            if (_HEADING_RE.match(cur) or _FENCE_RE.match(cur.strip())
                    or _QUOTE_RE.match(cur) or _LIST_RE.match(cur) or _HR_RE.match(cur)):
                break
            buf.append(cur.strip())
            i += 1
        if buf:
            out.append("<p>%s</p>" % "<br/>".join(_inline(b) for b in buf))

    return "".join(out)


if __name__ == "__main__":
    import sys
    src = sys.stdin.read() if len(sys.argv) < 2 or sys.argv[1] == "-" \
        else open(sys.argv[1], encoding="utf-8").read()
    sys.stdout.write(md_to_storage(src))
