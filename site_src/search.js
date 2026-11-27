/* ---- 본문 검색 (Ctrl K 팝업). 색인은 처음 검색할 때만 불러온다. 점수·구간 계산은 lib.js ---- */
(function(){
var B=document.body,root=B.dataset.root||"",lang=B.dataset.lang||"en",T=window.DOCS_UI||{},btn=document.getElementById("searchbtn");if(!btn)return;
var modal=document.createElement("div");modal.id="searchmodal";modal.hidden=true;
var panel=document.createElement("div");panel.className="panel";var box=document.createElement("input");box.type="search";box.placeholder=T.search||"Search...";
var res=document.createElement("div");res.id="results";panel.appendChild(box);panel.appendChild(res);modal.appendChild(panel);document.body.appendChild(modal);
var state="idle",docs=null;
function open(){modal.hidden=false;box.focus();box.select()}
function close(){modal.hidden=true}
btn.onclick=open;modal.addEventListener("mousedown",function(e){if(e.target===modal)close()});
document.addEventListener("keydown",function(e){if((e.ctrlKey||e.metaKey)&&(e.key==="k"||e.key==="K")){e.preventDefault();modal.hidden?open():close()}else if(e.key==="Escape"&&!modal.hidden)close()});
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
   var sn=document.createElement("span");if(i>=0){var from=Math.max(0,i-50);sn.appendChild(document.createTextNode(from?"...":""));mark(sn,d.x.slice(from,i+110),terms);sn.appendChild(document.createTextNode("..."))}
   a.appendChild(sn);res.appendChild(a)})})}
var timer;box.addEventListener("input",function(){clearTimeout(timer);timer=setTimeout(run,150)});
})();
