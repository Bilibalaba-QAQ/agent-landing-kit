# 终端实录内嵌配方(asciinema-player 单文件方案)

目标:在单文件 HTML slides 里内嵌一段**真文字渲染**的终端回放(逐字打命令、彩色输出、可调速),零外部请求。比 GIF 清晰、体积小、更有 AI 感。

## 材料(本 skill assets/ 已带)

- `asciinema-player.min.js` + `asciinema-player.css`(官方 v3.10.0 standalone,~250KB)
- `demo.cast` 示例录像(asciicast v2 格式)

## 三步内嵌

1. **备录像**:两种来源任选——
   - 真录:`asciinema rec demo.cast`(需装 asciinema CLI);
   - **手工合成(推荐,零依赖、零瑕疵)**:asciicast v2 就是 JSONL——首行 header + 每行一个事件 `[秒, "o", "文本"]`。用脚本按 40–60ms/字符生成打字事件即可拟真,ANSI 色码(如 `[38;5;79m`)上色。
2. **内联三件**:
   - `</head>` 前插 `<style>`(player css + 主题覆盖);
   - 主脚本前插 `<script>`(player js)+ `<script>const DEMO_CAST=<JSON字符串化的cast全文>;</script>`;
3. **slide 激活时创建播放器**:
   ```js
   AsciinemaPlayer.create({data: DEMO_CAST}, document.getElementById('asciicast'),
     {autoPlay:true, controls:false, fit:false,
      terminalFontFamily:'"SF Mono",Menlo,monospace', terminalFontSize:'13px'});
   ```
   重放前先 `instance.dispose()` 再重建。

## 主题覆盖(对齐赛博配色)

```css
#asciicast .ap-terminal{background:#070a0e !important;border:none;padding:12px 16px;}
#asciicast .ap-wrapper{background:transparent;}
```

## 坑

- cast header 的 `height`(行数)决定播放器高度,按实际输出行数 +1 设,别用默认 24;
- `fit:'width'` 会把字号放大到容器宽,slides 里通常太高——用 `fit:false` + 固定字号;
- 内联前查 min.js 里有无 `</script` 字样(v3.10.0 没有;有则替换为 `<\/script`);
- 保留一份纯 CSS/JS 打字机终端做兜底(模板 `.term` 即是),播放器不可用时降级。
