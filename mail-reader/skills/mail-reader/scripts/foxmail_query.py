#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""foxmail-query — Foxmail 本地邮件只读查询工具(零第三方依赖)。

数据源:~/Library/Containers/com.tencent.Foxmail/Data/Library/Foxmail/Profiles/
每账户一个 messages.db(SQLite,只读打开)+ Mail/*/*/<mailid>.mail(RFC822 原文)。

子命令:accounts / list / search / read / attachments
人名智能搜索:--from/--to 接受中文名,自动扩展 原名 / 全拼 / 声母缩写 / 姓全拼+名缩写。
"""

import argparse
import email
import email.policy
import glob
import html
import json
import os
import re
import sqlite3
import sys
import time
import unicodedata
from datetime import datetime
from html.parser import HTMLParser

PROFILES_ROOT = os.path.expanduser(
    "~/Library/Containers/com.tencent.Foxmail/Data/Library/Foxmail/Profiles"
)
DEFAULT_ACCOUNT = os.environ.get("FOXMAIL_ACCOUNT", "yourname@example.com")
TOOL_DIR = os.path.dirname(os.path.abspath(__file__))
NAMES_JSON = os.path.join(TOOL_DIR, "names.json")

# 多音字姓氏纠正(仅作用于人名首字;系统转换给的是常用读音,姓氏读音不同时以此为准)
SURNAME_FIX = {
    "曾": "zeng", "单": "shan", "解": "xie", "仇": "qiu", "区": "ou",
    "查": "zha", "朴": "piao", "乐": "yue", "种": "chong", "折": "she",
    "覃": "qin", "缪": "miao", "翟": "zhai", "任": "ren", "燕": "yan",
}

EMAIL_USER_RE = re.compile(r"([A-Za-z0-9._%+\-]+)@[A-Za-z0-9.\-]+")


# ---------------- 拼音 ----------------

def _cf_pinyin(text):
    """macOS CoreFoundation CFStringTransform 汉字→拼音(无声调)。失败返回 None。"""
    try:
        import ctypes
        import ctypes.util
        cf = ctypes.CDLL(ctypes.util.find_library("CoreFoundation"))
        cf.CFStringCreateWithCString.restype = ctypes.c_void_p
        cf.CFStringCreateWithCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint32]
        cf.CFStringCreateMutableCopy.restype = ctypes.c_void_p
        cf.CFStringCreateMutableCopy.argtypes = [ctypes.c_void_p, ctypes.c_long, ctypes.c_void_p]
        cf.CFStringTransform.restype = ctypes.c_bool
        cf.CFStringTransform.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_bool]
        cf.CFStringGetCString.restype = ctypes.c_bool
        cf.CFStringGetCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_long, ctypes.c_uint32]
        kutf8 = 0x08000100
        src = cf.CFStringCreateWithCString(None, text.encode("utf-8"), kutf8)
        mut = cf.CFStringCreateMutableCopy(None, 0, src)
        trans = cf.CFStringCreateWithCString(None, b"Any-Latin; Latin-ASCII", kutf8)
        if not cf.CFStringTransform(mut, None, trans, False):
            return None
        buf = ctypes.create_string_buffer(4096)
        if not cf.CFStringGetCString(mut, buf, 4096, kutf8):
            return None
        return buf.value.decode("utf-8")
    except Exception:
        return None


def _load_names_json():
    if os.path.exists(NAMES_JSON):
        try:
            with open(NAMES_JSON, encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[foxmail-query] 警告:names.json 解析失败:{e}", file=sys.stderr)
    return {}


def name_to_syllables(name):
    """中文名 → 拼音音节列表。优先级:names.json > pypinyin > CFStringTransform。
    拿不准的字返回 None 并提示。"""
    custom = _load_names_json()
    if name in custom:
        val = custom[name]
        return val.split() if isinstance(val, str) else list(val)
    try:
        from pypinyin import lazy_pinyin  # 环境已装则优先
        syl = lazy_pinyin(name)
        if name[0] in SURNAME_FIX:
            syl[0] = SURNAME_FIX[name[0]]
        return syl
    except ImportError:
        pass
    syllables = []
    for i, ch in enumerate(name):
        if i == 0 and ch in SURNAME_FIX:
            syllables.append(SURNAME_FIX[ch])
            continue
        py = _cf_pinyin(ch)
        if not py or not py.strip() or not py.strip().isascii():
            print(
                f"[foxmail-query] 提示:「{ch}」拼音拿不准,已跳过拼音扩展;"
                f"可在 {NAMES_JSON} 里为「{name}」补自定义映射。",
                file=sys.stderr,
            )
            return None
        syllables.append(py.strip().lower())
    return syllables


def has_cjk(s):
    return any("一" <= c <= "鿿" for c in s)


def person_matcher(query):
    """返回 match(field_text) 函数。中文名自动扩展多路 OR 匹配:
    ① 中文原名子串(含显示名,覆盖 Confluence 代发);
    ② 全拼子串(chenxingnuo);
    ③ 缩写(cxn / chenxn)——只对邮箱 @ 前用户名做精确匹配,防误伤。"""
    if not has_cjk(query):
        q = query.lower()
        return lambda text: q in (text or "").lower()

    syllables = name_to_syllables(query)
    full = "".join(syllables) if syllables else None
    abbrevs = set()
    if syllables and len(syllables) >= 2:
        abbrevs.add("".join(s[0] for s in syllables))            # 声母缩写 cxn
        abbrevs.add(syllables[0] + "".join(s[0] for s in syllables[1:]))  # 姓全拼+名缩写 chenxn

    def match(text):
        if not text:
            return False
        if query in text:
            return True
        low = text.lower()
        if full and full in low:
            return True
        if abbrevs:
            for user in EMAIL_USER_RE.findall(low):
                if user in abbrevs:
                    return True
        return False

    return match


# ---------------- 数据访问 ----------------

def list_accounts():
    if not os.path.isdir(PROFILES_ROOT):
        sys.exit(f"[foxmail-query] 未找到 Foxmail 数据目录:{PROFILES_ROOT}")
    return sorted(
        d for d in os.listdir(PROFILES_ROOT)
        if os.path.isfile(os.path.join(PROFILES_ROOT, d, "messages.db"))
    )


def resolve_accounts(account):
    all_acc = list_accounts()
    if account == "all":
        return all_acc
    if account not in all_acc:
        sys.exit(f"[foxmail-query] 账户不存在:{account}(现有:{', '.join(all_acc)})")
    return [account]


def open_db(account):
    db = os.path.join(PROFILES_ROOT, account, "messages.db")
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)  # 铁律:只读
    con.row_factory = sqlite3.Row
    return con


def folder_id(con, folder):
    """文件夹名/编号 → boxes.id。'all' 返回 None(不过滤)。"""
    if folder == "all":
        return None
    if folder.isdigit():
        return int(folder)
    cur = con.execute("SELECT id FROM boxes WHERE title = ?", (folder,))
    row = cur.fetchone()
    if not row:
        titles = [r["title"] for r in con.execute("SELECT title FROM boxes")]
        sys.exit(f"[foxmail-query] 文件夹不存在:{folder}(现有:{', '.join(titles)})")
    return row["id"]


def parse_date(s, end=False):
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            t = time.mktime(datetime.strptime(s, fmt).timetuple())
            if end and fmt == "%Y-%m-%d":
                t += 86399
            return int(t)
        except ValueError:
            continue
    sys.exit(f"[foxmail-query] 日期格式不对:{s}(用 YYYY-MM-DD 或 YYYY-MM-DD HH:MM)")


def query_mails(account, args, need_folder_name=False):
    """按 SQL 侧条件(文件夹/日期/未读/标题)取行,发件人/收件人在 Python 侧过滤。"""
    con = open_db(account)
    fid = folder_id(con, args.folder)
    sql = ["SELECT DISTINCT m.mailid, m.subject, m.sender, m.from_, m.to_, m.csender,",
           "m.date, m.readstat, m.attachment"]
    if need_folder_name:
        sql.append(", b.title AS folder")
    sql.append("FROM mailinfo m JOIN mail_box_info x ON m.mailid = x.mail_id")
    if need_folder_name:
        sql.append("LEFT JOIN boxes b ON x.mail_folderid = b.id")
    cond, params = [], []
    if fid is not None:
        cond.append("x.mail_folderid = ?"); params.append(fid)
    if getattr(args, "since", None):
        cond.append("m.date >= ?"); params.append(parse_date(args.since))
    if getattr(args, "until", None):
        cond.append("m.date <= ?"); params.append(parse_date(args.until, end=True))
    if getattr(args, "unread", False):
        cond.append("m.readstat = 0")
    if getattr(args, "subject", None):
        cond.append("m.subject LIKE ? ESCAPE '\\'")
        params.append("%" + args.subject.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_") + "%")
    if cond:
        sql.append("WHERE " + " AND ".join(cond))
    sql.append("ORDER BY m.date DESC")
    rows = con.execute(" ".join(sql), params).fetchall()
    con.close()

    if getattr(args, "from_", None):
        m = person_matcher(args.from_)
        rows = [r for r in rows if m(r["from_"]) or m(r["sender"]) or m(r["csender"])]
    if getattr(args, "to", None):
        m = person_matcher(args.to)
        rows = [r for r in rows if m(r["to_"])]
    return rows


def find_mail_file(mailid, account=None):
    """定位 <mailid>.mail 原文文件。优先指定/默认账户,找不到再扫全部。"""
    order = []
    if account and account != "all":
        order.append(account)
    else:
        order.append(DEFAULT_ACCOUNT)
    order += [a for a in list_accounts() if a not in order]
    for acc in order:
        hits = glob.glob(os.path.join(PROFILES_ROOT, acc, "Mail", "*", "*", f"{mailid}.mail"))
        if hits:
            return acc, hits[0]
    return None, None


def parse_mail_file(path):
    with open(path, "rb") as f:
        return email.message_from_binary_file(f, policy=email.policy.default)


# ---------------- HTML → 文本(保留表格结构) ----------------

class HtmlToText(HTMLParser):
    _BLOCK = {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "h5", "h6",
              "table", "ul", "ol", "blockquote", "section", "article"}
    _SKIP = {"style", "script", "head", "title", "meta"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out = []
        self._skip = 0
        self._in_row = False

    def handle_starttag(self, tag, attrs):
        if tag in self._SKIP:
            self._skip += 1
        elif tag == "tr":
            self._in_row = True
            self.out.append("\n")
        elif tag in ("td", "th"):
            self.out.append(" | ")
        elif tag in self._BLOCK:
            self.out.append("\n")

    def handle_endtag(self, tag):
        if tag in self._SKIP and self._skip:
            self._skip -= 1
        elif tag == "tr":
            self._in_row = False
        elif tag in self._BLOCK:
            self.out.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self.out.append(re.sub(r"\s+", " ", data))

    def text(self):
        raw = "".join(self.out)
        lines = [ln.strip() for ln in raw.splitlines()]
        cleaned, blank = [], 0
        for ln in lines:
            ln = re.sub(r"^\|\s*", "", ln).rstrip()
            if not ln:
                blank += 1
                if blank > 1:
                    continue
            else:
                blank = 0
            cleaned.append(ln)
        return "\n".join(cleaned).strip()


def html_to_text(src):
    p = HtmlToText()
    try:
        p.feed(src)
        p.close()
    except Exception:
        return re.sub(r"<[^>]+>", " ", html.unescape(src))
    return p.text()


def extract_body_text(msg):
    """取正文纯文本:优先 text/plain,否则 text/html 转文本。"""
    plain, htm = None, None
    for part in msg.walk():
        if part.get_content_maintype() != "text" or part.get_filename():
            continue
        try:
            content = part.get_content()
        except Exception:
            payload = part.get_payload(decode=True) or b""
            content = payload.decode(part.get_content_charset() or "utf-8", "replace")
        if part.get_content_subtype() == "plain" and plain is None:
            plain = content
        elif part.get_content_subtype() == "html" and htm is None:
            htm = content
    if plain and plain.strip():
        return plain.strip()
    if htm:
        return html_to_text(htm)
    return "(无文本正文)"


# ---------------- 输出 ----------------

def fmt_ts(ts):
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")


def print_rows(rows, account, show_account=False):
    for r in rows:
        flags = ("●" if r["readstat"] == 0 else " ") + ("📎" if r["attachment"] else "  ")
        acc = f"[{account}] " if show_account else ""
        folder = f" <{r['folder']}>" if "folder" in r.keys() and r["folder"] else ""
        sender = (r["from_"] or r["sender"] or "").strip().rstrip(";")
        print(f"{r['mailid']}\t{fmt_ts(r['date'])} {flags} {acc}{sender}{folder}\t{r['subject']}")


# ---------------- 子命令 ----------------

def cmd_accounts(_args):
    for acc in list_accounts():
        con = open_db(acc)
        n = con.execute("SELECT count(*) FROM mailinfo").fetchone()[0]
        con.close()
        mark = " (默认)" if acc == DEFAULT_ACCOUNT else ""
        print(f"{acc}\t{n} 封{mark}")


def cmd_list(args):
    accounts = resolve_accounts(args.account)
    total = 0
    for acc in accounts:
        rows = query_mails(acc, args, need_folder_name=(args.folder == "all"))
        rows = rows[: args.limit] if args.limit else rows
        print_rows(rows, acc, show_account=len(accounts) > 1)
        total += len(rows)
    print(f"—— 共 {total} 封", file=sys.stderr)


def cmd_search(args):
    kw = args.body.lower()
    accounts = resolve_accounts(args.account)
    total = scanned = 0
    t0 = time.time()
    for acc in accounts:
        rows = query_mails(acc, args)
        hits = []
        for r in rows:
            _, path = find_mail_file(r["mailid"], acc)
            if not path:
                continue
            scanned += 1
            try:
                msg = parse_mail_file(path)
                body = extract_body_text(msg)
            except Exception:
                continue
            if kw in body.lower() or kw in (msg.get("Subject") or "").lower():
                hits.append(r)
                if args.limit and len(hits) >= args.limit:
                    break
        print_rows(hits, acc, show_account=len(accounts) > 1)
        total += len(hits)
    print(f"—— 命中 {total} 封 / 扫描 {scanned} 封,耗时 {time.time()-t0:.1f}s"
          f"(范围大时建议加 --since 收窄)", file=sys.stderr)


def cmd_read(args):
    acc, path = find_mail_file(args.mailid, args.account)
    if not path:
        sys.exit(f"[foxmail-query] 找不到邮件原文文件:mailid={args.mailid}")
    msg = parse_mail_file(path)
    print(f"账户: {acc}")
    for h in ("Subject", "From", "To", "Cc", "Date"):
        if msg.get(h):
            print(f"{h}: {msg.get(h)}")
    atts = [p.get_filename() for p in msg.walk() if p.get_filename()]
    if atts:
        print(f"附件: {', '.join(atts)}")
    print("-" * 60)
    print(extract_body_text(msg))


def cmd_attachments(args):
    acc, path = find_mail_file(args.mailid, args.account)
    if not path:
        sys.exit(f"[foxmail-query] 找不到邮件原文文件:mailid={args.mailid}")
    msg = parse_mail_file(path)
    items = []
    for part in msg.walk():
        fn = part.get_filename()
        cid = (part.get("Content-ID") or "").strip("<>")
        if fn:
            items.append(("附件", fn, part))
        elif cid and part.get_content_maintype() == "image":
            ext = part.get_content_subtype()
            items.append(("内嵌图片", f"{cid}.{ext}", part))
    if not items:
        print("(无附件或内嵌图片)")
        return
    for i, (kind, name, part) in enumerate(items, 1):
        data = part.get_payload(decode=True) or b""
        print(f"{i}. [{kind}] {name}\t{len(data)} 字节\t{part.get_content_type()}")
        if args.save:
            os.makedirs(args.save, exist_ok=True)
            safe = re.sub(r"[/\\\0]", "_", name)
            out = os.path.join(args.save, safe)
            base, ext = os.path.splitext(out)
            n = 1
            while os.path.exists(out):
                out = f"{base}_{n}{ext}"; n += 1
            with open(out, "wb") as f:
                f.write(data)
            print(f"   已保存 → {out}")


# ---------------- 入口 ----------------

def add_common_filters(p, with_person=True):
    p.add_argument("--account", default=DEFAULT_ACCOUNT, help=f"账户,默认 {DEFAULT_ACCOUNT},可 all")
    p.add_argument("--folder", default="收件箱", help="文件夹名或编号,默认 收件箱,可 all")
    p.add_argument("--since", help="起始日期 YYYY-MM-DD")
    p.add_argument("--until", help="截止日期 YYYY-MM-DD")
    p.add_argument("--limit", type=int, default=50, help="最多条数,默认 50,0=不限")
    if with_person:
        p.add_argument("--from", dest="from_", help="发件人(支持中文名智能匹配)")
        p.add_argument("--to", help="收件人(支持中文名智能匹配)")
        p.add_argument("--subject", help="标题关键词")
        p.add_argument("--unread", action="store_true", help="只看未读")


def main():
    ap = argparse.ArgumentParser(prog="foxmail-query", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("accounts", help="列出所有账户及邮件总数")

    p = sub.add_parser("list", help="列邮件(组合筛选)")
    add_common_filters(p)

    p = sub.add_parser("search", help="正文关键词搜索(扫 .mail 文件)")
    p.add_argument("--body", required=True, help="正文关键词")
    add_common_filters(p)

    p = sub.add_parser("read", help="读邮件头+正文纯文本")
    p.add_argument("mailid", type=int)
    p.add_argument("--account", default=None, help="账户(可省,自动定位)")

    p = sub.add_parser("attachments", help="列出/提取附件与内嵌图片")
    p.add_argument("mailid", type=int)
    p.add_argument("--account", default=None, help="账户(可省,自动定位)")
    p.add_argument("--save", help="保存目录(不给则只列清单)")

    args = ap.parse_args()
    {"accounts": cmd_accounts, "list": cmd_list, "search": cmd_search,
     "read": cmd_read, "attachments": cmd_attachments}[args.cmd](args)


if __name__ == "__main__":
    main()
