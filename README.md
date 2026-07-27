# agent-landing-kit — 给 AI 新员工的入职装备

一句话定位:**把一个刚上岗的 AI 助手快速武装起来的六件套插件市场**——会看资讯、会查邮件、打得开内网站点、写得进内网文档、先找轮子再造轮子、还能做出漂亮的演示 slides。

**Codex 与 Claude Code 都能装**(同一个仓库带两套插件清单,各认各的)。

## 装法(推荐):把下面这段整段粘给你的 AI

> 请把 GitHub 公开仓 `Bilibalaba-QAQ/agent-landing-kit` 添加为插件市场并安装其中的插件。
> 你自己判断当前跑在哪个客户端,用对应的命令:
> - **Codex**:`codex plugin marketplace add Bilibalaba-QAQ/agent-landing-kit`,再逐个 `codex plugin add <插件名>@agent-landing-kit`
> - **Claude Code**:`claude plugin marketplace add Bilibalaba-QAQ/agent-landing-kit`,再逐个 `claude plugin install <插件名>@agent-landing-kit`
>
> 六个插件是:ai-briefing、mail-reader、conf-access、conf-writer、skill-scout、slide-forge。装完后请:
> ①用 ai-briefing 出一份今天的 AI 日报,验证装好了;
> ②告诉我 mail-reader 两条路径(macOS Foxmail 本地脚本 / IMAP 邮件 MCP)哪条适合我这台机器;
> ③conf-access 先别执行,等我从管理员处拿到内网域名与 IP;
> ④conf-writer 先只跑一次离线渲染自检(`render --text '# hi'`),等我给出目标页面地址再谈写入。

## 装法(手动):自己敲命令

```bash
# Codex
codex plugin marketplace add Bilibalaba-QAQ/agent-landing-kit
codex plugin add conf-writer@agent-landing-kit      # 换成你要的插件名;六件可逐个装

# Claude Code
claude plugin marketplace add Bilibalaba-QAQ/agent-landing-kit
claude plugin install conf-writer@agent-landing-kit
```

Claude Code 里也可以用 `/plugin` 交互式挑选。

## 六件一览

| 插件 | 做什么 | 适用前提 |
|---|---|---|
| `ai-briefing` | AI 资讯双技能:aihot 即时查询 + ai-daily 纯文本日报(公开只读 API,零凭据) | 无 |
| `mail-reader` | 邮件只读检索:列账户/筛邮件/搜正文/读单封/存附件 | 路径一需 macOS + Foxmail 客户端;其他环境走路径二(IMAP 邮件 MCP,见插件内指南) |
| `conf-access` | 内网站点(Confluence/Wiki)打不开?hosts 标记块一键钉到健康 IP,备份/幂等/可还原 | 域名与 IP 向你的网络管理员/团队群获取(不在本仓库) |
| `conf-writer` | 把 markdown 写进指定 Confluence 页面的指定位置:整页替换 / 追加 / 插到某个标题小节下 / 新建页面,默认 dry-run 预览 | 能访问目标 Confluence;浏览器已登录该站点即可零凭据使用 |
| `skill-scout` | 新需求先深搜 GitHub/skill 市场找现成能力,找不到才自建 | 无 |
| `slide-forge` | 赛博终端风 HTML 动效 slides:单文件零依赖离线放映,可内嵌 asciinema 终端实录 | 无 |

## 注意事项

- `mail-reader` 路径一零凭据只读;路径二需要你自己生成 IMAP 授权码,**自己填在本机,永不写进仓库或对话**。
- `conf-access` 写 `/etc/hosts` 需要 sudo,请自己回车确认;域名与 IP 只保存在你本机 `~/.config/conf-access/config`。
- `conf-writer` 默认 dry-run,不加 `--apply` 不会写入任何内容;走浏览器会话腿零凭据零配置,走 PAT 腿则 token 只存你本机 `~/.config/opc/conf-writer.env`(或 `~/.config/conf-writer/config`),**各人用各人的,不要互传**。
  它的浏览器会话腿产出的是一段自包含 JS:有浏览器工具的客户端可直接执行,没有的话把这段 JS 粘进浏览器开发者工具 Console 里跑,效果一样。
- `slide-forge` 附带的 asciinema-player 资产为 GPL-3.0,详见 `slide-forge/skills/slide-forge/assets/THIRD_PARTY.md`。

## License

MIT(见 `LICENSE`;slide-forge 内 asciinema-player 资产除外,按 THIRD_PARTY 标注为 GPL-3.0)。

维护:[Bilibalaba-QAQ](https://github.com/Bilibalaba-QAQ)
