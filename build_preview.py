"""Builds demo/talbista-demo.html: ONE self-contained file (fake backend + customer/driver/admin screens) that opens on any phone browser."""
import os, json
H = os.path.dirname(os.path.abspath(__file__)); SRC = os.path.dirname(os.path.dirname(H))
rd = lambda p: open(p, encoding="utf-8").read()
pages = {"customer": rd(f"{SRC}/index.html"), "driver": rd(f"{SRC}/driver.html"), "admin": rd(f"{SRC}/admin.html")}
mj = rd(f"{SRC}/map.js").replace("</script", "<\\/script")
pages = {k: v.replace('<script src="map.js"></script>', "<script>" + mj + "</script>") for k, v in pages.items()}
data = json.dumps(pages, ensure_ascii=False).replace("</", "<\\/").replace("<!--", "<\\!--")
tpl = '''<!doctype html>
<html lang="ar" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>طلبيستا - معاينة تجريبية</title>
<style>
:root{--g:#0b7a55;--paper:#e8eeeb;--ink:#14201c}@media(prefers-color-scheme:dark){:root{--paper:#0b100e;--ink:#e9f0ed}}
*{box-sizing:border-box}html,body{height:100%;margin:0}body{background:var(--paper);color:var(--ink);font:15px "Segoe UI",Tahoma,"Noto Sans Arabic",sans-serif;display:flex;flex-direction:column;align-items:center}
.bar{display:flex;gap:6px;padding:8px;width:100%;max-width:430px;padding-top:calc(8px + env(safe-area-inset-top))}.bar button{flex:1;padding:12px 2px;border-radius:12px;border:2px solid var(--g);background:none;color:var(--g);font:700 14px inherit;font-family:inherit}
.bar button.on{background:var(--g);color:#fff}.bar button.r{flex:0 0 auto;padding:12px 14px;border-color:#999;color:#777}
iframe{flex:1;width:100%;max-width:430px;border:0;background:#fff;border-radius:18px 18px 0 0;box-shadow:0 0 0 1px #0002}
#sp{position:fixed;inset:0;background:var(--g);display:flex;flex-direction:column;align-items:center;justify-content:center;gap:12px;color:#fff;transition:opacity .5s;z-index:9}#sp svg{width:96px;height:96px}#sp b{font-size:38px}
</style></head><body>
<div id="sp"><svg viewBox="0 0 100 100"><circle cx="50" cy="42" r="22" fill="#fff"/><polygon points="29,50 71,50 50,86" fill="#fff"/><circle cx="50" cy="42" r="10" fill="#0b7a55"/></svg><b>طلبيستا</b><span>معاينة تجريبية - بيانات وهمية</span></div>
<div class="bar"><button data-k="customer">زبون</button><button data-k="store">متجر</button><button data-k="driver">السائق</button><button data-k="admin">الإدارة</button><button class="r" id="rs">↺</button></div>
<iframe id="f" title="طلبيستا"></iframe>
<script>window.__tbShared=1;</script>
<script>__MOCK__</script>
<script>
const P=__PAGES__, KEY={store:['t','demo-store'],customer:['t','demo-customer'],driver:['dr','demo-driver'],admin:['at','demo-admin']};let cur='customer';
function inject(k){return '<script>window.__tbShared=1;window.__tbDemo=1;try{localStorage.getItem("x")}catch(e){Object.defineProperty(window,"localStorage",{value:(function(){var m={};return{getItem:function(a){return a in m?m[a]:null},setItem:function(a,b){m[a]=String(b)},removeItem:function(a){delete m[a]}}})()})}'
 +'try{["t","dr","at","dr_S","role"].forEach(function(x){localStorage.removeItem(x)});localStorage.setItem('+JSON.stringify(KEY[k][0])+','+JSON.stringify(KEY[k][1])+')'+(k==='store'?';localStorage.setItem("role","STORE")':'')+'}catch(e){}window.fetch=function(u,o){return parent.TBMock.fetch(u,o)};<\\/script></head>'}
function show(k){cur=k;document.querySelectorAll('[data-k]').forEach(b=>b.classList.toggle('on',b.dataset.k===k));document.getElementById('f').srcdoc=P[k==='store'?'customer':k].replace('</head>',()=>inject(k))}
document.querySelectorAll('[data-k]').forEach(b=>b.onclick=()=>show(b.dataset.k));document.getElementById('rs').onclick=()=>{TBMock.reset();show(cur)};
show('customer');setTimeout(()=>{const s=document.getElementById('sp');s.style.opacity=0;setTimeout(()=>s.remove(),500)},1500);
</script></body></html>'''
out = tpl.replace("__MOCK__", rd(f"{H}/demo-mock.js").replace("</script", "<\\/script")).replace("__PAGES__", data)
os.makedirs(f"{SRC}/demo", exist_ok=True); open(f"{SRC}/demo/talbista-demo.html", "w", encoding="utf-8").write(out); print(len(out), "bytes")
