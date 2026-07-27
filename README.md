# agent-landing-kit — 给 AI 新员工的入职装备

一句话定位:**把一个刚上岗的 AI 助手(Claude Code / Codex 等)快速武装起来的六件套插件市场**——会看资讯、会查邮件、打得开内网站点、写得进内网文档、先找轮子再造轮子、还能做出漂亮的演示 slides。

## 六件一览

| 插件 | 做什么 | 适用前提 |
|---|---|---|
| `ai-briefing` | AI 资讯双技能:aihot 即时查询 + ai-daily 纯文本日报(公开只读 API,零凭据) | 无 |
| `mail-reader` | 邮件只读检索:列账户/筛邮件/搜正文/读单封/存附件 | 路径一需 macOS + Foxmail 客户端;其他环境走路径二(IMAP 邮件 MCP,见插件内指南) |
| `conf-access` | 内网站点(Confluence/Wiki)打不开?hosts 标记块一键钉到健康 IP,备份/幂等/可还原 | 域名与 IP 向你的网络管理员/团队群获取(不在本仓库) |
| `conf-writer` | 把 markdown 写进指定 Confluence 页面的指定位置:整页替换 / 追加 / 插到某个标题小节下 / 新建页面,默认 dry-run 预览 | 能访问目标 Confluence;浏览器已登录该站点即可零凭据使用 |
| `skill-scout` | 新需求先深搜 GitHub/skill 市场找现成能力,找不到才自建 | 无 |
| `slide-forge` | 赛博终端风 HTML 动效 slides:单文件零依赖离线放映,可内嵌 asciinema 终端实录 | 无 |

## 安装方式一:终端两条命令

```bash
claude plugin marketplace add Bilibalaba-QAQ/agent-landing-kit
claude plugin install ai-briefing@agent-landing-kit   # 换成你要的插件名;六件可逐个装
```

或在 Claude Code 会话里用 `/plugin` 交互式挑选。

## 安装方式二:AI 版(直接粘给你的 Claude Code / Codex)

> 请添加插件市场 `Bilibalaba-QAQ/agent-landing-kit`(GitHub 公开仓),然后把其中的六个插件 ai-briefing、mail-reader、conf-access、conf-writer、skill-scout、slide-forge 全部安装。装完后:①用 ai-briefing 给我出一份今天的 AI 日报验证;②告诉我 mail-reader 两条路径(macOS Foxmail 本地脚本 / IMAP 邮件 MCP)哪条适合当前机器;③conf-access 先不要执行,等我从管理员处拿到内网域名与 IP 再说;④conf-writer 先只跑 `render` 自检渲染,等我给出目标页面地址再谈写入。

## 注意事项

- `mail-reader` 路径一零凭据只读;路径二需要你自己生成 IMAP 授权码,**自己填在本机,永不写进仓库或对话**。
- `conf-access` 写 `/etc/hosts` 需要 sudo,请自己回车确认;域名与 IP 只保存在你本机 `~/.config/conf-access/config`。
- `conf-writer` 默认 dry-run,不加 `--apply` 不会写入任何内容;走浏览器会话腿零凭据零配置,走 PAT 腿则 token 只存你本机 `~/.config/opc/conf-writer.env`(或 `~/.config/conf-writer/config`),**各人用各人的,不要互传**。
- `slide-forge` 附带的 asciinema-player 资产为 GPL-3.0,详见 `slide-forge/skills/slide-forge/assets/THIRD_PARTY.md`。

## License

MIT(见 `LICENSE`;slide-forge 内 asciinema-player 资产除外,按 THIRD_PARTY 标注为 GPL-3.0)。

维护:[Bilibalaba-QAQ](https://github.com/Bilibalaba-QAQ)
