(function(){
var B=document.body,root=B.dataset.root||"",cur=B.dataset.slug||"",lang=B.dataset.lang||"en",T=window.DOCS_UI||{};
function el(tag,cls,text){var e=document.createElement(tag);if(cls)e.className=cls;if(text!=null)e.textContent=text;return e}
function copyText(t,done){
 if(navigator.clipboard&&window.isSecureContext)navigator.clipboard.writeText(t).then(done);
 else{var x=document.createElement("textarea");x.value=t;document.body.appendChild(x);x.select();document.execCommand("copy");x.remove();done()}}
var tog=document.getElementById("navtoggle");if(tog)tog.onclick=function(){var o=B.classList.toggle("navopen");tog.setAttribute("aria-expanded",o?"true":"false")};

/* ---- 상단 탭 + 사이드바 ---- */
var data=window.DOCS_NAV,tabsEl=document.getElementById("tabs"),nav=document.getElementById("nav");
var first=DocsLib.navFirst,has=DocsLib.navHas;
if(data&&nav){
 var curPath=cur+".html",active=null;
 data.tabs.forEach(function(t){if(!active&&has(t,curPath))active=t});
 if(!active)active=data.tabs[0];
 data.tabs.forEach(function(t){if(t.hidden)return;var a=el("a",t===active?"active":"",t.n);a.href=root+first(t);tabsEl.appendChild(a)});
 var box=el("input");box.type="search";box.placeholder=T.filter||"Filter pages...";box.setAttribute("aria-label",T.filter||"Filter pages");nav.appendChild(box);
 var wrap=el("div","tree");nav.appendChild(wrap);
 function leaf(n){var a=el("a","leaf",n.t);a.href=root+n.p;if(n.p===curPath)a.setAttribute("aria-current","page");return a}
 function build(nodes,parent,depth){nodes.forEach(function(n){
  if(n.p){parent.appendChild(leaf(n));return}
  if(depth===0){var sec=el("section","grp");sec.appendChild(el("h5",null,n.g));build(n.c,sec,1);parent.appendChild(sec)}
  else{var d=el("details","sub");d.appendChild(el("summary",null,n.g));var inner=el("div","subbox");build(n.c,inner,depth+1);d.appendChild(inner);if(has(n,curPath))d.open=true;parent.appendChild(d)}})}
 build(active.c,wrap,0);
 function reset(){wrap.querySelectorAll("details.sub").forEach(function(d){d.open=!!d.querySelector("[aria-current]")})}
 var cl=wrap.querySelector("[aria-current]");if(cl)nav.scrollTop=Math.max(0,cl.getBoundingClientRect().top-nav.getBoundingClientRect().top+nav.scrollTop-nav.clientHeight/2);
 box.oninput=function(){var q=box.value.trim().toLowerCase();
  wrap.querySelectorAll("a.leaf").forEach(function(a){a.style.display=DocsLib.labelMatches(a.textContent,q)?"":"none"});
  wrap.querySelectorAll("details.sub,section.grp").forEach(function(d){var vis=!q||Array.prototype.some.call(d.querySelectorAll("a.leaf"),function(a){return a.style.display!=="none"});
   d.style.display=vis?"":"none";if(q&&d.tagName==="DETAILS")d.open=vis});
  if(!q)reset()}}

/* ---- 본문 탭, 앵커 이동 ---- */
function selectTab(b){var g=b.closest(".tabs");Array.prototype.forEach.call(g.children,function(c){
 if(c.classList.contains("tab-list")){Array.prototype.forEach.call(c.children,function(x){var on=x===b;x.classList.toggle("active",on);x.setAttribute("aria-selected",on?"true":"false");x.tabIndex=on?0:-1})}
 else if(c.classList.contains("tab-panel"))c.classList.toggle("active",c.id===b.dataset.tab)})}
document.addEventListener("click",function(e){var b=e.target.closest&&e.target.closest(".tab-btn");if(b)selectTab(b)});
document.addEventListener("keydown",function(e){var b=e.target.closest&&e.target.closest(".tab-btn");if(!b)return;
 var btns=Array.prototype.slice.call(b.parentElement.querySelectorAll(".tab-btn")),n=DocsLib.tabIndex(e.key,btns.indexOf(b),btns.length);
 if(n===null)return;e.preventDefault();selectTab(btns[n]);btns[n].focus()});
function reveal(t){for(var e=t;e&&e!==B;e=e.parentElement){
 if(e.classList.contains("tab-panel")){var btn=e.parentElement.querySelector('.tab-btn[data-tab="'+e.id+'"]');if(btn)selectTab(btn)}
 if(e.tagName==="DETAILS")e.open=true}}
var anchorKey=DocsLib.anchorKey;
function goHash(){var h=location.hash.slice(1);if(!h)return;var t;try{t=document.getElementById(decodeURIComponent(h))}catch(e){}
 if(!t){var k=anchorKey(h),c=document.querySelectorAll("article [id]");for(var i=0;i<c.length;i++){if(anchorKey(c[i].id)===k){t=c[i];break}}}
 if(t){reveal(t);t.scrollIntoView()}}
window.addEventListener("hashchange",goHash);goHash();

/* ---- 우측 목차 (이 페이지에서) ---- */
var toc=document.getElementById("toc");
if(toc){var hs=Array.prototype.filter.call(document.querySelectorAll("article h2[id],article h3[id]"),function(h){return !h.closest(".tab-panel,details")});
 if(hs.length<2){toc.hidden=true}
 else{toc.appendChild(el("p","toc-title",T.toc||"On this page"));var ul=el("ul"),links=[],inline=el("details","toc-inline"),iul=el("ul");
  inline.appendChild(el("summary",null,T.toc||"On this page"));
  hs.forEach(function(h){var c=h.cloneNode(true),a0=c.querySelector(".anchor");if(a0)a0.remove();
   var txt=c.textContent.trim(),cls=DocsLib.tocClass(h.tagName);
   var li=el("li",cls),a=el("a",null,txt);a.href="#"+h.id;li.appendChild(a);ul.appendChild(li);links.push(a);
   var li2=el("li",cls),a2=el("a",null,txt);a2.href="#"+h.id;li2.appendChild(a2);iul.appendChild(li2)});
  toc.appendChild(ul);inline.appendChild(iul);hs[0].parentNode.insertBefore(inline,hs[0]); /* 좁은 화면용 접는 목차 */
  iul.addEventListener("click",function(e){if(e.target.closest("a"))inline.open=false});
  var tick=false;function spy(){tick=false;var tops=hs.map(function(h){return h.getBoundingClientRect().top}),
   cur=DocsLib.currentIndex(tops,150,window.innerHeight+window.scrollY>=document.documentElement.scrollHeight-4);
   links.forEach(function(a,i){if(i===cur)a.setAttribute("aria-current","true");else a.removeAttribute("aria-current")});
   var on=links[cur];if(on){var r=on.getBoundingClientRect(),t=toc.getBoundingClientRect();if(r.top<t.top+40||r.bottom>t.bottom-20)toc.scrollTop+=r.top-t.top-t.height/2}}
  window.addEventListener("scroll",function(){if(!tick){tick=true;requestAnimationFrame(spy)}},{passive:true});spy()}}

/* ---- 페이지 복사, 코드 복사 ---- */
var cp=document.getElementById("copypage"),src=document.getElementById("md-src");
if(cp&&src){var lab=cp.querySelector("span"),orig=lab.textContent;
 cp.onclick=function(){copyText(JSON.parse(src.textContent),function(){lab.textContent=T.copied||"Copied";setTimeout(function(){lab.textContent=orig},1200)})}}
var ICON='<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="8" y="3" width="8" height="4" rx="1"/><path d="M16 5h2a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h2"/></svg>';
document.querySelectorAll("pre").forEach(function(pre){var b=el("button","copy");b.type="button";b.innerHTML=ICON;b.title=T.copy||"Copy";b.setAttribute("aria-label",T.copy||"Copy");
 b.onclick=function(){copyText(pre.querySelector("code").innerText,function(){b.textContent=T.copied||"Copied";setTimeout(function(){b.innerHTML=ICON},1200)})};
 pre.appendChild(b)});
})();
