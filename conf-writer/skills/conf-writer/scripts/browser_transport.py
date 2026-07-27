#!/usr/bin/env python3
"""浏览器会话传输腿:生成一段自包含 JS,借用户已登录的 Confluence 会话调同一套 REST API。

用在拿不到 PAT 的场景。凭据是浏览器里的会话 cookie,本工具不接触、不存储。
生成的 JS 交给浏览器工具(claude-in-chrome 的 javascript_tool)在 Confluence 站点标签页执行。

写入位置逻辑与 conf_writer.build_body 一一对应(replace / append / prepend / under-heading);
两处实现须同步改,改完用 tests/test_placement.py 验 python 侧、在真站点跑一次 dry-run 验 JS 侧。
"""

import json

# Confluence 对非 GET 请求做 XSRF 校验,带此头即放行(官方约定)。
_JS = r"""
const R = %s;
const H = {'Content-Type':'application/json','X-Atlassian-Token':'no-check'};
const GET = async u => { const r = await fetch(u,{credentials:'same-origin',headers:{Accept:'application/json'}});
  if(!r.ok) throw new Error('GET '+r.status+' '+u); return r.json(); };

// 标题内文:去行内标签 + 还原实体,与 conf_writer.heading_text 对齐。
const htext = s => { const d = document.createElement('div');
  d.innerHTML = s.replace(/<[^>]+>/g,''); return (d.textContent||'').replace(/ /g,' ').trim(); };

function place(existing, add, mode, heading){
  if(mode==='replace') return add;
  if(mode==='append')  return existing + add;
  if(mode==='prepend') return add + existing;
  const re = /<h([1-6])\b[^>]*>([\s\S]*?)<\/h\1>/gi;
  const hits = []; let m;
  while((m = re.exec(existing))) hits.push({lvl:+m[1], text:htext(m[2]), start:m.index});
  const i = hits.findIndex(h => h.text === heading);
  if(i < 0) throw new Error('目标页面没有标题「'+heading+'」。现有标题:'+(hits.map(h=>h.text).join('、')||'(无)'));
  let end = existing.length;
  for(const h of hits.slice(i+1)) if(h.lvl <= hits[i].lvl){ end = h.start; break; }
  return existing.slice(0,end) + add + existing.slice(end);
}

const EXP = '?expand=body.storage,version,space';
let page = null;
if(R.pageId){
  page = await GET('/rest/api/content/'+encodeURIComponent(R.pageId)+EXP);
}else if(R.space && R.title){
  const q = await GET('/rest/api/content?type=page&spaceKey='+encodeURIComponent(R.space)
                      +'&title='+encodeURIComponent(R.title)+'&expand=body.storage,version,space');
  page = (q.results || [])[0] || null;
}

let out;
if(page === null){
  if(!(R.space && R.title)) throw new Error('目标页面不存在;新建须同时给空间与标题。');
  let ancestors;
  if(R.parentId){ ancestors = [{id:String(R.parentId)}]; }
  else if(R.parentTitle){
    const q = await GET('/rest/api/content?type=page&spaceKey='+encodeURIComponent(R.space)
                        +'&title='+encodeURIComponent(R.parentTitle));
    const p = (q.results || [])[0];
    if(!p) throw new Error('找不到父页面「'+R.parentTitle+'」。');
    ancestors = [{id:String(p.id)}];
  }
  const payload = {type:'page', title:R.title, space:{key:R.space},
                   body:{storage:{value:R.addition, representation:'storage'}}};
  if(ancestors) payload.ancestors = ancestors;
  if(!R.apply){
    out = {动作:'新建页面', 空间:R.space, 标题:R.title, 父页面:R.parentId||R.parentTitle||'(空间根)',
           正文字符数:R.addition.length, 结果:'dry-run,未写入'};
  }else{
    const r = await fetch('/rest/api/content',{method:'POST',credentials:'same-origin',headers:H,
                                               body:JSON.stringify(payload)});
    const j = await r.json();
    if(!r.ok) throw new Error('创建失败 '+r.status+':'+(j.message||''));
    out = {动作:'新建页面', 标题:j.title, 页面ID:j.id, 结果:'✓ 已创建',
           链接:(j._links&&j._links.base||'')+((j._links&&j._links.webui)||'')};
  }
}else{
  const existing = ((page.body||{}).storage||{}).value || '';
  const body = place(existing, R.addition, R.mode, R.heading);
  const v = (page.version||{}).number || 0;
  if(!R.apply){
    out = {动作:'更新页面', 标题:page.title, 页面ID:page.id, 模式:R.mode,
           标题定位:R.heading||'—', 版本:'v'+v+' → v'+(v+1),
           正文字符数:existing.length+' → '+body.length, 结果:'dry-run,未写入'};
  }else{
    const payload = {id:String(page.id), type:'page', title:page.title,
                     space:{key:(page.space||{}).key},
                     body:{storage:{value:body, representation:'storage'}},
                     version:{number:v+1, message:R.message||'conf-writer 写入'}};
    const r = await fetch('/rest/api/content/'+encodeURIComponent(page.id),
                          {method:'PUT',credentials:'same-origin',headers:H,body:JSON.stringify(payload)});
    const j = await r.json();
    if(!r.ok) throw new Error('写入失败 '+r.status+':'+(j.message||'')
                              +(r.status===409?'(版本冲突:页面已被他人改动,请重新跑一次)':''));
    out = {动作:'更新页面', 标题:j.title, 页面ID:j.id, 版本:'v'+((j.version||{}).number),
           结果:'✓ 已写入', 链接:(j._links&&j._links.base||'')+((j._links&&j._links.webui)||'')};
  }
}
JSON.stringify(out, null, 1)
"""


def build_script(addition, page_id=None, space=None, title=None, mode="replace",
                 heading=None, parent_id=None, parent_title=None,
                 message=None, apply=False):
    payload = {"addition": addition, "pageId": page_id, "space": space, "title": title,
               "mode": mode, "heading": heading, "parentId": parent_id,
               "parentTitle": parent_title, "message": message, "apply": bool(apply)}
    return _JS % json.dumps(payload, ensure_ascii=False)
