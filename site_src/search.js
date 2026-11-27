/* ---- 본문 검색 (Ctrl K 팝업). 색인은 처음 검색할 때만 불러온다. 점수·구간 계산은 lib.js ---- */
(function(){
var B=document.body,root=B.dataset.root||"",lang=B.dataset.lang||"en",T=window.DOCS_UI||{},btn=document.getElementById("searchbtn");if(!btn)return;
var modal=document.createElement("div");modal.id="searchmodal";modal.hidden=true;
var panel=document.createElement("div");panel.className="panel";panel.setAttribute("role","dialog");panel.setAttribute("aria-modal","true");panel.setAttribute("aria-label",T.search||"Search");
var box=document.createElement("input");box.type="search";box.placeholder=T.search||"Search...";box.setAttribute("aria-label",T.search||"Search");
var res=document.createElement("div");res.id="results";res.setAttribute("aria-live","polite");panel.appendChild(box);panel.appendChild(res);modal.appendChild(panel);document.body.appendChild(modal);
var state="idle",docs=null;
var opener=null;
function open(){opener=document.activeElement;modal.hidden=false;box.focus();box.select()}
function close(){modal.hidden=true;if(opener&&opener.focus&&document.contains(opener))opener.focus();opener=null}
btn.onclick=open;modal.addEventListener("mousedown",function(e){if(e.target===modal)close()});
document.addEventListener("keydown",function(e){if((e.ctrlKey||e.metaKey)&&(e.key==="k"||e.key==="K")){e.preventDefault();modal.hidden?open():close()}else if(e.key==="Escape"&&!modal.hidden)close()});
/* 키보드: Tab 은 입력창과 결과 사이를 돌고(밖으로 나가지 않음), 위/아래 화살표는 결과를 오간다 */
modal.addEventListener("keydown",function(e){
 var hits=Array.prototype.slice.call(res.querySelectorAll("a.hit")),all=[box].concat(hits),cur=all.indexOf(document.activeElement);
 if(e.key==="Tab"){e.preventDefault();all[DocsLib.cycle(cur,all.length,e.shiftKey?-1:1)].focus()}
 else{var n=DocsLib.listIndex(e.key,cur-1,hits.length);if(n===null)return;e.preventDefault();(n<0?box:hits[n]).focus()}});
function load(cb){if(docs)return cb();if(state==="loading")return;state="loading";res.textContent=T.loading||"Loading...";
 var s=document.createElement("script");s.src=root+"search-data-"+lang+".js";
 s.onload=function(){docs=DocsLib.prepare(window.DOCS_SEARCH);state="ready";cb()};
 s.onerror=function(){state="idle";res.textContent=T.no_index||"Search index not found."};document.head.appendChild(s)}
function mark(parent,text,terms){DocsLib.markSegments(text,terms).forEach(function(s){
 if(s[0]){var m=document.createElement("mark");m.textContent=s[1];parent.appendChild(m)}else parent.appendChild(document.createTextNode(s[1]))})}
function run(){var q=box.value.trim().toLowerCase();res.textContent="";var terms=DocsLib.searchTerms(q);if(!terms.length)return;
 load(function(){if(box.value.trim().toLowerCase()!==q)return;res.textContent="";var hits=DocsLib.rankDocs(docs,terms);
  var info=document.createElement("div");info.className="info";info.textContent=hits.length?(T.n_match||"{n}").replace("{n}",hits.length):(T.none||"");res.appendChild(info);
  hits.slice(0,30).forEach(function(h){var d=h.d,a=document.createElement("a");a.className="hit";
   var head=DocsLib.pickHeading(d,terms);
   a.href=root+d.p+(head?"#"+head[1]:"");var b=document.createElement("b");mark(b,d.t,terms);a.appendChild(b);
   var i=DocsLib.firstMatchIndex(d,terms);
   var sn=document.createElement("span");if(i>=0){var r=DocsLib.snippetRange(d,i);sn.appendChild(document.createTextNode(r[2]?"...":""));mark(sn,d.x.slice(r[0],r[1]),terms);sn.appendChild(document.createTextNode("..."))}
   a.appendChild(sn);res.appendChild(a)})})}
var timer;box.addEventListener("input",function(){clearTimeout(timer);timer=setTimeout(run,150)});
})();
