#!/usr/bin/env python3
"""conf-writer — 把 markdown 内容写进指定 Confluence 页面。零第三方依赖。

能力边界:只管「内容 → 指定位置」的投递,不产内容。谁调都一样(人在对话框贴、
写作 agent 生成后调),接口都是「目标 + markdown」。

配置(按优先级:命令行 > 环境变量 > ~/.config/opc/conf-writer.env):
    CONF_BASE_URL   Confluence 站点根,如 http://confluence.example.com
    CONF_PAT        Personal Access Token(推荐,Confluence 7.9+)
    CONF_USER/CONF_PASS   老版本无 PAT 时的 Basic 认证回退

默认 dry-run:只渲染并给出 diff 预览,加 --apply 才真正落笔。
"""

import argparse
import base64
import difflib
import html
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
from md2storage import md_to_storage  # noqa: E402

# 本机配置层 loader(能力分层规范 §四):出仓包里在 lib/,仓内在 capability-packager/lib/。
sys.path.insert(0, os.path.join(_HERE, "lib"))
sys.path.insert(0, os.path.abspath(os.path.join(
    _HERE, "../../capability-packager/lib")))
from opc_config import get as opc_get  # noqa: E402

CAPABILITY = "conf-writer"
CONFIG_PATH = os.path.expanduser("~/.config/opc/%s.env" % CAPABILITY)
# 独立安装(非 OPC 环境)的备选位置,格式相同,均为 KEY=VALUE 纯文本。
FALLBACK_CONFIG = os.path.expanduser("~/.config/conf-writer/config")
KEYS = ("CONF_BASE_URL", "CONF_PAT", "CONF_USER", "CONF_PASS")
TIMEOUT = 20


# ---------- 配置 ----------

def load_config():
    cfg = {k: opc_get(CAPABILITY, k) for k in KEYS}
    if not any(cfg.values()) and os.path.exists(FALLBACK_CONFIG):
        with open(FALLBACK_CONFIG, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    if k.strip() in KEYS:
                        cfg[k.strip()] = v.strip().strip("'\"")
    return cfg


def base_url(cfg, override=None):
    url = override or cfg.get("CONF_BASE_URL")
    if not url:
        die("未配置站点根。跑一次 `conf_writer.py setup`,或用 --base-url / --url 指定。\n"
            "  配置文件位置:%s" % CONFIG_PATH)
    return url.rstrip("/")


def auth_header(cfg):
    if cfg.get("CONF_PAT"):
        return "Bearer " + cfg["CONF_PAT"]
    if cfg.get("CONF_USER") and cfg.get("CONF_PASS"):
        raw = "%s:%s" % (cfg["CONF_USER"], cfg["CONF_PASS"])
        return "Basic " + base64.b64encode(raw.encode()).decode()
    die("未配置凭据。跑一次 `conf_writer.py setup --with-pat`,\n"
        "  或手工在 %s(或 %s)里设 CONF_PAT(推荐)/ CONF_USER + CONF_PASS。\n"
        "  提示:改用浏览器会话腿(browser-script)则完全不需要凭据。"
        % (CONFIG_PATH, FALLBACK_CONFIG))


def parse_page_url(url):
    """从页面链接里拆出站点根 / pageId / 空间 / 标题,三种常见形态都吃。

    .../spaces/<KEY>/pages/<ID>/<Title>   新版路径
    .../pages/viewpage.action?pageId=<ID> 经典路径
    .../display/<KEY>/<Page+Title>        经典短链
    """
    u = urllib.parse.urlsplit(url)
    if not u.scheme or not u.netloc:
        die("看不懂这个页面地址:%s" % url)
    out = {"base": "%s://%s" % (u.scheme, u.netloc), "page_id": None,
           "space": None, "title": None}
    qs = urllib.parse.parse_qs(u.query)
    if qs.get("pageId"):
        out["page_id"] = qs["pageId"][0]
    parts = [p for p in u.path.split("/") if p]
    for i, seg in enumerate(parts):
        if seg == "spaces" and i + 1 < len(parts):
            out["space"] = urllib.parse.unquote(parts[i + 1])
        if seg == "pages" and i + 1 < len(parts) and parts[i + 1].isdigit():
            out["page_id"] = parts[i + 1]
        if seg == "display" and i + 1 < len(parts):
            out["space"] = urllib.parse.unquote(parts[i + 1])
            if i + 2 < len(parts):
                out["title"] = urllib.parse.unquote(parts[i + 2]).replace("+", " ")
    if not (out["page_id"] or (out["space"] and out["title"])):
        die("这个地址里既没有 pageId 也没有「空间+标题」,无法定位:%s" % url)
    return out


def apply_url_target(args):
    """--url 给出的信息填进 args(已显式给出的参数优先,不覆盖)。"""
    if not getattr(args, "url", None):
        return
    info = parse_page_url(args.url)
    if not args.page_id:
        args.page_id = info["page_id"]
    if not args.space:
        args.space = info["space"]
    if not args.title:
        args.title = info["title"]
    if not getattr(args, "base_url", None):
        args.base_url = info["base"]


def die(msg, code=1):
    sys.stderr.write("✗ %s\n" % msg)
    sys.exit(code)


# ---------- HTTP ----------

def request(cfg, method, path, payload=None, need_auth=True, base=None):
    url = base_url(cfg, base) + path
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Accept", "application/json")
    if data:
        req.add_header("Content-Type", "application/json")
    if need_auth:
        req.add_header("Authorization", auth_header(cfg))
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:400]
        try:
            detail = json.loads(detail).get("message", detail)
        except Exception:
            pass
        if e.code == 401:
            detail += "(凭据无效或已过期:确认 PAT 未过期、账号有该空间权限)"
        die("HTTP %s %s\n  %s" % (e.code, url, detail))
    except urllib.error.URLError as e:
        die("连接失败 %s:%s\n  不在公司内网时无法访问,请先接入内网。" % (url, e.reason))


# ---------- 页面操作 ----------

def get_page(cfg, page_id):
    return request(cfg, "GET", "/rest/api/content/%s?expand=body.storage,version,space,ancestors"
                   % urllib.parse.quote(str(page_id)))


def find_page(cfg, space, title):
    q = urllib.parse.urlencode({"spaceKey": space, "title": title, "type": "page",
                                "expand": "body.storage,version,space"})
    res = request(cfg, "GET", "/rest/api/content?" + q)
    results = res.get("results") or []
    return results[0] if results else None


def page_url(cfg, page, base=None):
    webui = ((page.get("_links") or {}).get("webui")) or ""
    return base_url(cfg, base) + webui if webui else \
        base_url(cfg, base) + "/pages/viewpage.action?pageId=%s" % page.get("id")


_HEADING_RE = re.compile(r"<h([1-6])\b[^>]*>(.*?)</h\1>", re.I | re.S)
_TAG_RE = re.compile(r"<[^>]+>")


def heading_text(markup):
    """标题内文:去掉行内标签并还原 HTML 实体,便于按肉眼所见的文字匹配。"""
    return html.unescape(_TAG_RE.sub("", markup)).replace("\xa0", " ").strip()


def insert_under_heading(existing, addition, heading):
    """把 addition 插到指定标题所辖小节的末尾(下一个同级或更高级标题之前)。"""
    target = heading.strip()
    matches = list(_HEADING_RE.finditer(existing))
    for idx, m in enumerate(matches):
        text = heading_text(m.group(2))
        if text == target:
            level = int(m.group(1))
            end = len(existing)
            for later in matches[idx + 1:]:
                if int(later.group(1)) <= level:
                    end = later.start()
                    break
            return existing[:end] + addition + existing[end:]
    titles = [heading_text(m.group(2)) for m in matches]
    die("目标页面里没有标题「%s」。现有标题:%s"
        % (target, "、".join(titles) if titles else "(无)"))


def build_body(mode, existing, addition, heading=None):
    if mode == "replace":
        return addition
    if mode == "append":
        return existing + addition
    if mode == "prepend":
        return addition + existing
    if mode == "under-heading":
        return insert_under_heading(existing, addition, heading)
    die("未知写入模式:%s" % mode)


def pretty(storage):
    """给 diff 用的粗排版:块级标签前断行,便于逐块比对。"""
    s = re.sub(r"(<(?:h[1-6]|p|ul|ol|li|table|tr|blockquote|hr|ac:structured-macro)\b)",
               r"\n\1", storage)
    return [ln for ln in s.split("\n") if ln.strip()]


def show_diff(old, new, label):
    diff = list(difflib.unified_diff(pretty(old), pretty(new),
                                     fromfile="当前 " + label, tofile="写入后 " + label,
                                     lineterm="", n=1))
    if not diff:
        print("(内容无变化)")
        return
    for line in diff[:80]:
        print(line)
    if len(diff) > 80:
        print("... 其余 %d 行差异略" % (len(diff) - 80))


# ---------- 子命令 ----------

def read_content(args):
    if args.file:
        return open(args.file, encoding="utf-8").read()
    if args.text is not None:
        return args.text
    if not sys.stdin.isatty():
        return sys.stdin.read()
    die("没有内容输入。用 --file / --text,或从标准输入管道传入。")


def cmd_probe(args, cfg):
    """免凭据探活:确认站点可达、REST 在线、读出版本。"""
    base = base_url(cfg, args.base_url)
    try:
        with urllib.request.urlopen(base + "/login.action", timeout=TIMEOUT) as r:
            html = r.read().decode("utf-8", "replace")
    except Exception as e:
        die("站点不可达 %s:%s" % (base, e))
    ver = re.search(r'ajs-version-number"\s+content="([^"]+)"', html)
    print("站点:%s" % base)
    print("版本:%s" % (ver.group(1) if ver else "未识别"))
    if ver:
        parts = tuple(int(x) for x in re.findall(r"\d+", ver.group(1))[:2])
        print("PAT 支持:%s" % ("是(7.9+)" if parts >= (7, 9) else "否,用 CONF_USER/PASS"))
    req = urllib.request.Request(base + "/rest/api/space")
    try:
        urllib.request.urlopen(req, timeout=TIMEOUT)
        print("REST API:开放(匿名可读)")
    except urllib.error.HTTPError as e:
        print("REST API:%s" % ("在线,需认证(正常)" if e.code == 401 else "返回 %s" % e.code))
    except Exception as e:
        die("REST 不可达:%s" % e)


def cmd_whoami(args, cfg):
    me = request(cfg, "GET", "/rest/api/user/current")
    print("✓ 凭据有效:%s (%s)" % (me.get("displayName", "?"), me.get("username")
                                  or me.get("userKey", "?")))


def cmd_setup(args, cfg):
    """写本机配置。凭据只从交互输入读,绝不接受命令行参数(免落 shell 历史)。"""
    import getpass
    base = args.base_url
    if not base:
        base = input("Confluence 站点根(如 http://wiki.example.internal):").strip()
    if not base.startswith(("http://", "https://")):
        die("站点根须以 http:// 或 https:// 开头。")
    lines = ["# conf-writer 本机配置(勿入仓库)", "CONF_BASE_URL=" + base.rstrip("/")]
    if args.with_pat:
        pat = getpass.getpass("粘贴 Personal Access Token(不回显,留空跳过):").strip()
        if pat:
            lines.append("CONF_PAT=" + pat)
    os.makedirs(os.path.dirname(CONFIG_PATH), mode=0o700, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    os.chmod(CONFIG_PATH, 0o600)
    print("✓ 已写入 %s(600)" % CONFIG_PATH)
    print("  站点:%s" % base.rstrip("/"))
    print("  凭据:%s" % ("已存 PAT" if any(l.startswith("CONF_PAT=") for l in lines)
                        else "未设(走浏览器会话腿即可,无需凭据)"))


def cmd_browser_script(args, cfg):
    """产出浏览器会话腿要执行的 JS(不联网、不需要凭据)。"""
    from browser_transport import build_script
    addition = md_to_storage(read_content(args))
    if not addition.strip():
        die("渲染结果为空,拒绝生成写入脚本。")
    sys.stdout.write(build_script(
        addition, page_id=args.page_id, space=args.space, title=args.title,
        mode=args.mode, heading=args.heading, parent_id=args.parent_id,
        parent_title=args.parent_title, message=args.message, apply=args.apply))
    sys.stdout.write("\n")


def cmd_render(args, cfg):
    sys.stdout.write(md_to_storage(read_content(args)))
    sys.stdout.write("\n")


def cmd_get(args, cfg):
    page = resolve_page(cfg, args, required=True)
    print("标题:%s" % page["title"])
    print("页面 ID:%s" % page["id"])
    print("空间:%s" % (page.get("space") or {}).get("key", "?"))
    print("版本:%s" % (page.get("version") or {}).get("number", "?"))
    print("链接:%s" % page_url(cfg, page, args.base_url))
    if args.raw:
        print("--- storage ---")
        print(((page.get("body") or {}).get("storage") or {}).get("value", ""))


def resolve_page(cfg, args, required=False):
    if args.page_id:
        return get_page(cfg, args.page_id)
    if args.space and args.title:
        page = find_page(cfg, args.space, args.title)
        if page is None and required:
            die("空间 %s 下没有标题为「%s」的页面。" % (args.space, args.title))
        return page
    die("必须指定目标:--page-id,或 --space 加 --title。")


def cmd_write(args, cfg):
    markdown = read_content(args)
    addition = md_to_storage(markdown)
    if not addition.strip():
        die("渲染结果为空,拒绝写入。")

    page = resolve_page(cfg, args)

    if page is None:
        # 新建
        if not (args.space and args.title):
            die("目标页面不存在;新建须同时给 --space 与 --title。")
        payload = {"type": "page", "title": args.title,
                   "space": {"key": args.space},
                   "body": {"storage": {"value": addition, "representation": "storage"}}}
        parent = args.parent_id
        if not parent and args.parent_title:
            p = find_page(cfg, args.space, args.parent_title)
            if not p:
                die("找不到父页面「%s」。" % args.parent_title)
            parent = p["id"]
        if parent:
            payload["ancestors"] = [{"id": str(parent)}]
        print("动作:在空间 %s 新建页面「%s」%s"
              % (args.space, args.title, "(父页面 %s)" % parent if parent else ""))
        print("正文:%d 字符 storage" % len(addition))
        if not args.apply:
            print("\n[dry-run] 未写入。确认无误后加 --apply 执行。")
            return
        created = request(cfg, "POST", "/rest/api/content", payload)
        print("✓ 已创建:%s" % page_url(cfg, created, args.base_url))
        return

    # 更新已有页面
    existing = ((page.get("body") or {}).get("storage") or {}).get("value", "")
    new_body = build_body(args.mode, existing, addition, args.heading)
    version = (page.get("version") or {}).get("number", 0)

    print("动作:更新页面「%s」(id=%s,当前版本 v%s → v%s,模式 %s%s)"
          % (page["title"], page["id"], version, version + 1, args.mode,
             ",标题「%s」下" % args.heading if args.mode == "under-heading" else ""))
    print("链接:%s" % page_url(cfg, page, args.base_url))
    print("正文:%d → %d 字符\n" % (len(existing), len(new_body)))
    show_diff(existing, new_body, page["title"])

    if not args.apply:
        print("\n[dry-run] 未写入。确认无误后加 --apply 执行。")
        return

    payload = {"id": str(page["id"]), "type": "page", "title": page["title"],
               "space": {"key": (page.get("space") or {}).get("key")},
               "body": {"storage": {"value": new_body, "representation": "storage"}},
               "version": {"number": version + 1, "message": args.message or "conf-writer 写入"}}
    updated = request(cfg, "PUT", "/rest/api/content/%s" % page["id"], payload)
    print("\n✓ 已写入 v%s:%s"
          % ((updated.get("version") or {}).get("number", "?"),
             page_url(cfg, updated, args.base_url)))


# ---------- 入口 ----------

def main():
    ap = argparse.ArgumentParser(
        prog="conf-writer",
        description="把 markdown 内容写进指定 Confluence 页面(默认 dry-run)。")
    ap.add_argument("--base-url", help="覆盖 CONF_BASE_URL")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add_target(p):
        p.add_argument("--url", help="直接粘页面地址(自动拆出站点/空间/页面 ID)")
        p.add_argument("--page-id", help="目标页面 ID")
        p.add_argument("--space", help="空间 key")
        p.add_argument("--title", help="页面标题")

    def add_content(p):
        p.add_argument("--file", help="markdown 文件路径")
        p.add_argument("--text", help="markdown 文本(直接给)")

    p = sub.add_parser("setup", help="写本机配置(站点根;可选存 PAT)")
    p.add_argument("--with-pat", action="store_true",
                   help="同时交互式录入 PAT(不回显,不走命令行参数)")
    p.set_defaults(fn=cmd_setup)

    sub.add_parser("probe", help="免凭据探活:站点/版本/REST 状态").set_defaults(fn=cmd_probe)
    sub.add_parser("whoami", help="验证凭据并显示当前身份").set_defaults(fn=cmd_whoami)

    p = sub.add_parser("render", help="只渲染 markdown→storage,不联网")
    add_content(p)
    p.set_defaults(fn=cmd_render)

    p = sub.add_parser("get", help="读取页面信息")
    add_target(p)
    p.add_argument("--raw", action="store_true", help="打印 storage 原文")
    p.set_defaults(fn=cmd_get)

    p = sub.add_parser("write", help="写入页面(默认 dry-run,--apply 才落笔)")
    add_target(p)
    add_content(p)
    p.add_argument("--mode", default="replace",
                   choices=["replace", "append", "prepend", "under-heading"],
                   help="replace=整页替换(默认) append=追加到末尾 "
                        "prepend=插到开头 under-heading=插到指定标题小节末尾")
    p.add_argument("--heading", help="under-heading 模式下的目标标题文本")
    p.add_argument("--parent-id", help="新建页面时的父页面 ID")
    p.add_argument("--parent-title", help="新建页面时的父页面标题")
    p.add_argument("--message", help="版本备注")
    p.add_argument("--apply", action="store_true", help="真正写入")
    p.set_defaults(fn=cmd_write)

    p = sub.add_parser("browser-script",
                       help="产出浏览器会话腿的 JS(无 PAT 时用;不联网不需凭据)")
    add_target(p)
    add_content(p)
    p.add_argument("--mode", default="replace",
                   choices=["replace", "append", "prepend", "under-heading"])
    p.add_argument("--heading", help="under-heading 模式下的目标标题文本")
    p.add_argument("--parent-id", help="新建页面时的父页面 ID")
    p.add_argument("--parent-title", help="新建页面时的父页面标题")
    p.add_argument("--message", help="版本备注")
    p.add_argument("--apply", action="store_true",
                   help="生成真正写入的脚本(不加则生成 dry-run 脚本)")
    p.set_defaults(fn=cmd_browser_script)

    args = ap.parse_args()
    apply_url_target(args)
    if getattr(args, "mode", None) == "under-heading" and not args.heading:
        die("--mode under-heading 必须同时给 --heading。")
    args.fn(args, load_config())


if __name__ == "__main__":
    main()
