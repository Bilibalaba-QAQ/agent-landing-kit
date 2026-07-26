---
name: conf-access
description: 一条命令打通打不开的内网站点(Confluence/Wiki/内部系统)——把域名用 /etc/hosts 标记块钉到健康入口 IP,双网段/切网无感。只写一个标记块,先备份、幂等、可一键还原,不碰代理不影响本地网络。域名与 IP 从本地 config 或环境变量读取,首次安装交互式询问。触发词:Confluence 打不开、wiki 打不开、内网站点访问、hosts 配置、conf 访问。
---

# conf-access(内网站点 hosts 一键钉)

## 背景(什么时候用)

不少公司内网站点(Confluence/Wiki/内部系统)的域名 DNS 正解指向的节点在部分网段(尤其 WiFi)超时,而站点的网关/接入层 IP 在各网段均健康。把域名用 hosts 钉到那个健康 IP,即可双网段稳定访问、切网无感。

**域名与 IP 不在本仓库里**——向你的网络管理员/团队群获取,首次安装时填入,只保存在你自己机器的 `~/.config/conf-access/config`(600 权限)。内网 IP 属内部信息,请勿外传。

## 配置(四选一;域名与 IP 由团队内部提供——公司群/分享现场向管理员获取)

1. **命令行带参(推荐,AI 对话式安装一条命令走通)**:`install --domain <域名> --ip <IP>`;
2. **环境变量**:`CONF_DOMAIN=… CONF_IP=… sudo -E bash … install`;
3. **交互式**:什么都不设,直接 install,脚本询问后保存;
4. **手工写 config**:`~/.config/conf-access/config` 两行 `CONF_DOMAIN=…` / `CONF_IP=…`。

任一来源首次生效都会自动落到本地 config(600 权限),下次直接 `install` 免配。

## 安装(一条命令)

```bash
# 已有本地 config / 走交互式:
sudo bash <本skill目录>/scripts/conf-access.sh install

# 带参直配(把 <域名>/<IP> 换成团队内部提供的真值;示例值仅为占位):
sudo bash <本skill目录>/scripts/conf-access.sh install --domain wiki.example.internal --ip 203.0.113.10
```

脚本行为(全部可审计,见源码):
1. 备份 `/etc/hosts` → `/etc/hosts.bak-conf-access-<时间戳>`;
2. 幂等写入标记块(重复执行不叠加):
   ```
   # conf-access begin
   203.0.113.10 wiki.example.internal
   # conf-access end
   ```
3. 刷新 DNS 缓存并 curl 验证(2xx/3xx 视为通);
4. 打印卸载命令。

## 卸载(一键还原)/ 查看状态

```bash
sudo bash <本skill目录>/scripts/conf-access.sh uninstall   # 只删标记块,hosts 其余内容原样保留
bash <本skill目录>/scripts/conf-access.sh status           # 看当前标记块与本地配置
```

## 边界

- 只动 `/etc/hosts` 的标记块;不碰代理、DNS 服务器、任何网络配置。
- 执行需 sudo(改系统 hosts 文件):AI 应把命令交给用户自己回车,不代输密码。
- 若日后 IP 失效(验证 000/超时),先卸载,再向网络管理员确认新 IP、重跑 install。
- 测试/沙箱:`CONF_HOSTS_FILE=/tmp/hosts.sandbox` 可把写入指向普通文件(无需 sudo)。
