---
name: conf-writer
tier: company
config: [CONF_BASE_URL]
description: 把已经写好的 markdown 内容投递到指定 Confluence 页面的指定位置——整页替换 / 追加 / 插到某个标题小节下,支持新建页面。零凭据可用(借浏览器已登录会话),默认 dry-run 出预览,--apply 才落笔。只管投递不产内容,可挂给任意写作 agent 当「发布」动作。触发词:写到 conf、写进 Confluence、更新 wiki 页面、同步到 conf、发布到 Confluence、conf 页面追加。
---

# conf-writer(Confluence 内容投递)

## 这个 skill 管什么

**只管一件事:把给定的 markdown 内容,写到给定的 Confluence 位置。** 内容从哪来不管——
用户在对话框里直接给是它,写作 agent 按规则生成完调它也是它。接口恒定:

> (目标位置,markdown) → 转 storage format → 创建或更新页面

不产内容、不定文体、不限题材。要生成内容,那是调用方的事。

## 生效条件自检(动手前先过一遍)

| 条件 | 不满足会怎样 | 怎么办 |
|---|---|---|
| 能访问到目标 Confluence | 脚本报连接失败 | 内网站点先接入内网;域名打不开可配合 `conf-access` skill |
| 有一条可用的传输腿 | 无法认证 | 见下「两条传输腿」,浏览器会话腿零凭据、优先用 |
| 目标页面已锚定 | 不知道往哪写 | 见下「开工前必须澄清的四件事」 |
| 对目标页面有编辑权限 | 写入报 403 | 找页面所有者或空间管理员开权限 |

## 开工前必须澄清的四件事

**信息不全就别猜、别试写**——先向用户问清下面四项,缺哪项问哪项。写错地方的代价远高于多问一句。

1. **站点**:哪个 Confluence?(走浏览器会话腿时,只要浏览器停在那个站点上即可,不必单独配)
2. **落点**:哪个空间、哪个页面?**最省事的做法是让用户直接把页面地址粘过来**,
   `--url` 能自动拆出站点、空间与页面 ID。若用户只说得出标题,就用 `--space` + `--title` 定位;
   若页面还不存在,须问清空间 key 与父页面。
3. **写法**:是整页替换,还是追加到末尾 / 插到某个小节下?**默认不要用 `replace`**——
   除非用户明确说「整页重写」。不确定就问。
4. **内容**:markdown 正文从哪来(用户直接给 / 上游 agent 生成 / 读某个文件)。

澄清完先跑一次 **dry-run** 把「会写到哪、改多少字符、版本从几到几」摆给用户看,得到确认再 `--apply`。

## 两条传输腿:先看哪条能用

两条腿走的是**同一套 Confluence REST API**,写入质量完全一致,只是认证方式不同。

| | 腿 A:浏览器会话(默认) | 腿 B:PAT |
|---|---|---|
| 凭据 | **完全不需要**,借用户浏览器里已登录的会话 | 需要 Personal Access Token |
| 配置 | **零配置** | 需配站点根与 token |
| 前提 | 浏览器开着且已登录该 Confluence(有无浏览器工具都行,见下) | 站点 7.9+ 且允许创建 PAT |
| 无人值守 | 不行(定时任务用不了) | 可以 |
| 怎么跑 | `browser-script` 出 JS,交浏览器工具执行 | `write` 子命令直接跑 |

**不少公司站点禁用或不开放 PAT 创建**;拿不到 token 时走腿 A,能力不打折。

### 腿 A:浏览器会话(零凭据零配置)

生成一段自包含 JS,交给浏览器工具在 **已登录 Confluence 的标签页** 里执行:

```bash
python3 <本skill目录>/scripts/conf_writer.py browser-script \
    --url "<把页面地址粘这里>" --file 内容.md --mode append > /tmp/cw.js
```

把 `/tmp/cw.js` 的内容拿到浏览器里执行,三种方式任选(标签页须停在该 Confluence 站点上,
同源才带得上会话):

- 客户端自带浏览器工具的,直接执行(Claude Code 的 `claude-in-chrome` `javascript_tool`、
  Codex 的 browser / chrome 插件都行);
- **没有浏览器工具也不受影响**:让用户把这段 JS 粘进浏览器开发者工具 Console 回车,
  效果完全一样(F12 或 ⌥⌘I 打开 Console);
- 首次粘贴时 Chrome 可能要求先手动输入 `allow pasting` 才允许粘贴代码,照提示做即可。

不加 `--apply` 生成的是 dry-run 脚本,只回报「会改成什么样」,不写入;
确认后加 `--apply` 重新生成再执行。

脚本自己处理 XSRF(带 `X-Atlassian-Token: no-check`),执行完返回一段 JSON 小结。
**注意**:浏览器工具可能拦截疑似 cookie / query string 的返回内容,所以脚本只回报计数与
标题,不回吐页面正文片段——要看正文用腿 B 的 `get`,或直接在浏览器里看。

### 腿 B:PAT(可无人值守)

一条命令配好(站点根必填;PAT 交互式录入、不回显、不落 shell 历史):

```bash
python3 <本skill目录>/scripts/conf_writer.py setup --with-pat
```

写进 `~/.config/opc/conf-writer.env`(600 权限,纯 `KEY=VALUE` 文本;
独立安装也可放 `~/.config/conf-writer/config`)。手工配等价于:

```
CONF_BASE_URL=http://wiki.example.internal
CONF_PAT=你自己的 Personal Access Token
```

PAT 从 Confluence 右上角头像 → Settings → Personal Access Tokens 创建(勾写权限)。
**各人用各人的**,别互传;写入记录会记在你名下。站点低于 7.9 没有此功能,
改填 `CONF_USER` / `CONF_PASS` 走 Basic 认证。配好先验:`conf_writer.py whoami`。

站点版本与 REST 状态可免凭据探活:`conf_writer.py probe`。

## 用法

脚本下称 `CW`(= `<本skill目录>/scripts/conf_writer.py`)。两条腿共用同一套参数。

**定位目标**:`--url` 直接粘页面地址最省事(三种常见链接形态都吃:`/spaces/KEY/pages/ID/…`、
`/pages/viewpage.action?pageId=…`、`/display/KEY/Title`);也可以用 `--page-id`,
或 `--space` 加 `--title` 按标题找;都找不到就是新建(须给 `--space` + `--title`)。

**给内容**:`--file 文件.md`、`--text "..."`,或直接从标准输入管道传入。

**选位置**(`--mode`):

| mode | 效果 |
|---|---|
| `replace`(默认) | 整页正文替换 |
| `append` | 追加到页面末尾 |
| `prepend` | 插到页面开头 |
| `under-heading` | 插到 `--heading` 指定标题所辖小节的末尾(下一个同级或更高级标题之前) |

`--heading` 按**肉眼看到的标题文字**匹配(内部会去掉加粗等标签、还原 `&amp;` 一类实体)。

```bash
# 预览(不写入)
python3 CW write --url "<页面地址>" --file 周报.md --mode append

# 确认后落笔
python3 CW write --url "<页面地址>" --file 周报.md --mode append --apply

# 插到某个标题下
python3 CW write --url "<页面地址>" --file 进展.md \
    --mode under-heading --heading "本周进展" --apply

# 新建页面挂到父页面下
python3 CW write --space TEAM --title "2026-07 月报" --parent-title "月报归档" \
    --file 月报.md --apply
```

读现状与离线渲染:`CW get --url "<页面地址>" [--raw]`(腿 B)、`CW render --file x.md`(不联网)。

## 铁律

- **默认 dry-run**。不带 `--apply` 只出预览,一个字节都不会写。给用户看过预览再 `--apply`;
  挂给全自动 agent 管线时才由调用方直接带 `--apply`。
- **replace 会覆盖整页**。目标页面是别人的地盘时,优先用 `append` / `under-heading`,
  别拿 `replace` 图省事。
- **写入前先读版本号,提交时 +1**;若别人在这中间改过,Confluence 会拒绝提交而不是
  静默覆盖——报版本冲突就重新跑一次。
- **凭据只走本机配置文件或浏览器会话**,不进对话、不写进仓库、不硬编码站点地址。

## markdown 支持范围

标题 / 段落 / 有序无序列表(含嵌套)/ 表格 / 代码块(转 code 宏,自动映射语言别名)/
引用 / 分割线 / 链接 / 图片 / 粗斜体 / 行内代码 / 删除线;`[TOC]` 转目录宏;
GFM 提示块 `> [!WARNING]` 转 Confluence 对应的 info/note/tip/warning 宏。

要写转换器覆盖不到的高级宏,用 ```storage 围栏包住原生 storage format 片段,**原样直通**:

    ```storage
    <ac:structured-macro ac:name="children" ac:schema-version="1"/>
    ```

## 边界

- 需要能访问到目标 Confluence 的网络环境(内网站点通常要求接入内网);
  网络不通时脚本会明确报连接失败。
- 转换器覆盖常用 markdown;极复杂排版(嵌套表格、任务列表、脚注)不保证保真,
  这类内容建议拆简或用 storage 围栏直写。
- 附件上传、页面删除、权限修改**不在**本 skill 范围内。
- 自检脚本自身是否健康:`python3 <本skill目录>/scripts/conf_writer.py render --text '# hi'`
  应输出 `<h1>hi</h1>`,不需要网络与凭据。
